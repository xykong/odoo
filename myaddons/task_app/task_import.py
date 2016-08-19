# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import base64
import csv
import itertools
import logging
import operator
import time

import xlrd

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from openerp.osv import orm
from openerp.tools.translate import _

FIELDS_RECURSION_LIMIT = 2
ERROR_PREVIEW_BYTES = 200
_logger = logging.getLogger(__name__)

from openerp.osv import osv, fields


class task_import(osv.osv_memory):
    """ Language Import """

    _name = "task.import"
    # _description = "Todo Task Import"

    _columns = {
        'import_type': fields.selection([('purchases', 'Purchase Orders'),
                                         ('suppliers', 'Suppliers'),
                                         ], 'Import Type'),
        'binary_field': fields.binary('Your binary field', required=True),
        'filename': fields.char('Filename'),
        'combine_names': fields.boolean('Combine names', default=True,
                                        help="If you enable this option, product name will generate by combine stock "
                                             "and product type name."),
    }

    def _get_picking_location(self, cr, uid, name, context=None):
        company = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id
        stock_location_obj = self.pool.get('stock.location')
        warehouse_obj = self.pool.get('stock.warehouse')

        name = name.encode('utf8')

        wh_ids = warehouse_obj.search(cr, uid,
                                      [('company_id', '=', company.id),
                                       ('name', '=', name)],
                                      context=context)

        if len(wh_ids) == 0:
            raise osv.except_osv(_('Not Found!'), _('没有找到对应的仓库:' + name))

        wh = warehouse_obj.browse(cr, uid, wh_ids[0], context=context)

        return {
            'picking_type_id': wh.in_type_id.id,
            'location_id': wh.lot_stock_id.id
        }

        # location_ids = stock_location_obj.search(cr, uid,
        #                                          [('company_id', '=', company.id),
        #                                           ('complete_name', 'ilike', name + ' / 库存')],
        #                                          context=context)
        # # _logger.info('location_ids: %s', location_ids)
        # if len(location_ids) == 0:
        #     raise osv.except_osv(_('Not Found!'), _('没有找到对应的仓库:' + name))
        #
        # type_obj = self.pool.get('stock.picking.type')
        # type_ids = type_obj.search(cr, uid,
        #                            [('code', '=', 'incoming'), ('default_location_dest_id', '=', location_ids[0])],
        #                            context=context)
        # # _logger.info('type_ids: %s', type_ids)
        # if len(type_ids) == 0:
        #     raise osv.except_osv(_('Not Found!'), _('没有找到对应的仓库:' + name))
        #
        # return {'picking_type_id': type_ids[0],
        #         'location_id': location_ids[0]}

    def _get_or_create_product(self, cr, uid, item, context=None):
        product_obj = self.pool.get('product.template')

        product_ids = product_obj.search(cr, uid, [('name', 'in', [item['name']])], context=context)
        if len(product_ids) != 0:
            # _logger.info('product %s is already created. product_ids: %s', item['name'], product_ids)
            return product_ids

        if 'type' not in item:
            item['type'] = 'consu'

        vals = {
            'name': item['name'],
            'type': item['type'],
            'categ_id': 1,
            'uom_id': 1,
            'uom_po_id': 1,
        }
        product_ids = [product_obj.create(cr, uid, vals, context=context)]
        _logger.info('%s product created: product_id: %s', item['name'], product_ids)

        return product_ids

    def _get_or_create_partner(self, cr, uid, item, context=None):
        partner_obj = self.pool.get('res.partner')

        categories = []
        if 'categories' in item:
            categories = [self._get_or_create_category(cr, uid, c) for c in item['categories']]
            item['category_id'] = [(6, 0, categories)]
            del item['categories']

        partner_ids = partner_obj.search(cr, uid, [('name', 'in', [item['name']])], context=context)
        if len(partner_ids) != 0:
            # _logger.info('supplier %s is already created. partner_ids: %s', item['name'], partner_ids)

            for partner in partner_obj.browse(cr, uid, partner_ids, context=context):
                if len(categories) != 0:
                    _logger.info('supplier partner_ids: %s', partner.name)
                    partner.write({'category_id': [(4, categories)]})

                if ('mobile' in item) and item['mobile'] != partner.mobile:
                    comment = "%s.mobile:%s\n%s" % (time.strftime('%Y-%m-%d'), item['mobile'], partner.comment)
                    partner.write({'mobile': item['mobile'], 'comment': comment})

            return partner_ids

        # create a partner.
        if 'customer' not in item:
            item['customer'] = False

        item['supplier'] = True
        item['customer'] = False

        if 'mobile' in item:
            item['comment'] = "%s.mobile:%s" % (time.strftime('%Y-%m-%d'), item['mobile'])

        partner_ids = [partner_obj.create(cr, uid, item, context=context)]

        _logger.info('%s supplier created: partner_id: %s', item['name'], partner_ids)

        return partner_ids

    def _check_import_file_columes(self, colnames):
        try_fields = ['日期', '煤品种', '供应商', '车牌号', '电话', '运费单价', '净重', '单价', '库房', '客户名']
        for f in try_fields:
            if f not in colnames:
                raise osv.except_osv(_('Error!'), _('导入文件缺少数据列: ' + f))

    def _retrieve_items(self, cr, uid, ids, context=None):
        this = self.browse(cr, uid, ids[0])
        (record,) = self.browse(cr, uid, [id], context=context)

        record.file = base64.decodestring(this.binary_field)
        items = []

        # read csv file.
        import_fields = []
        try:
            options = {'headers': True, 'quoting': '"', 'separator': ',', 'encoding': 'gb2312'}
            try_fields = ['日期', '煤品种', '供应商', '车牌号', '电话', '运费单价', '净重', '单价', '库房', '客户名']

            data, import_fields = self._convert_import_data(record, try_fields, options, context=context)
        except:
            pass
        if len(import_fields) != 0:
            self._check_import_file_columes(import_fields)

            _logger.info('importing %d rows...', len(data))

            _logger.info('header: %s', import_fields)
            for d in data:
                items.append(dict(zip(import_fields, d)))
                # _logger.info('import item: %s', d)

            return items

        # read xls file.
        book = None
        try:
            record.file = base64.decodestring(this.binary_field)
            book = xlrd.open_workbook(file_contents=record.file)

        except:
            pass

        if book is not None:

            _logger.info('book sheets: %s', len(book.sheets()))

            table = book.sheet_by_index(0)
            nrows = table.nrows  # 行数

            if nrows < 2:
                raise osv.except_osv(_('Error!'), _('导入文件没有采购数据。'))

            items = []
            colnames = [c.encode('utf8') for c in table.row_values(0)]  # 某一行数据

            self._check_import_file_columes(colnames)

            for rownum in range(1, nrows):
                row = table.row_values(rownum)
                if row:
                    app = {}
                for i in range(len(colnames)):
                    if colnames[i] == '日期':
                        app[colnames[i]] = xlrd.xldate.xldate_as_datetime(row[i], 0).strftime('%Y-%m-%d')
                    else:
                        app[colnames[i]] = row[i]

                for i in range(len(colnames)):
                    if colnames[i] == '煤品种' and this.combine_names:
                        app[colnames[i]] = app['库房'] + '.' + row[i]

                items.append(app)
            return items

        raise osv.except_osv(_('Error!'), _('导入文件格式不正确，数据导入失败。'))

    def do_test_case(self, cr, uid, ids, context=None):
        _logger.info('do_test_case!')

        product_obj = self.pool.get('product.product')
        product_ids = product_obj.search(cr, uid, [('name', 'in', ['三八'])], context=context)

        result = dict.fromkeys(ids, False)
        for product in product_obj.browse(cr, uid, product_ids, context=context):
            price_extra = 0.0
            for variant_id in product.attribute_value_ids:
                _logger.info('variant_id.name: ' + variant_id.name)
                _logger.info('variant_id.attribute_id.name: ' + variant_id.attribute_id.name)
                for price_id in variant_id.price_ids:
                    if price_id.product_tmpl_id.id == product.product_tmpl_id.id:
                        price_extra += price_id.price_extra
            result[product.id] = price_extra

        return True

    def import_task(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        items = self._retrieve_items(cr, uid, ids, context=context)

        # this = self.browse(cr, uid, ids[0])
        # if this.combine_names:
        #     for i in items:
        #

        _logger.info('items: %s', items)

        # # suppliers = [index for index, field in enumerate(fields) if field]
        # suppliers = [(d[4]) for d in data]
        #
        # for s in suppliers:
        #     _logger.info('supplier: %s', s)
        #
        # _logger.info('suppliers %d rows...', len(suppliers))
        #
        # suppliers = list(set(suppliers))
        # _logger.info('suppliers %d rows...', len(suppliers))
        #
        # category = self._get_or_create_category(cr, uid, '运输车辆')
        # _logger.info('category: %s', category)
        #
        # partner_obj = self.pool.get('res.partner')
        # partner_ids = partner_obj.search(cr, uid, [('name', 'in', suppliers)], context=context)
        # _logger.info('partner_ids: %s', partner_ids)
        #
        # imported_supplier = 0
        # for d in data:
        #     partner_ids = partner_obj.search(cr, uid, [('name', 'in', [d[3]])], context=context)
        #     if len(partner_ids) != 0:
        #         _logger.info('supplier %s is already created. partner_ids: %s', d[3], partner_ids)
        #         continue
        #
        #     item = {
        #         'customer': False,
        #         'name': d[3],
        #         'mobile': d[4],
        #         'supplier': True,
        #         'category_id': [(6, 0, [category])]
        #     }
        #     partner_id = [partner_obj.create(cr, uid, item, context=context)]
        #     imported_supplier += 1
        #     # partner_obj.write(cr, uid, partner_id[0], item, context=context)
        #     _logger.info('%s supplier created: partner_id: %s', d[3], partner_id)
        #
        # _logger.info('%d suppliers import done.', imported_supplier)
        #
        # ########################################################################################
        # category = self._get_or_create_category(cr, uid, '客户')
        #
        # imported_supplier = 0
        # customers = set([x[9] for x in data])
        # for d in customers:
        #     partner_ids = partner_obj.search(cr, uid, [('name', 'in', [d])], context=context)
        #     if len(partner_ids) != 0 or len(d) == 0:
        #         _logger.info('customers %s is already created. partner_ids: %s', d, partner_ids)
        #         continue
        #
        #     item = {
        #         'customer': True,
        #         'name': d,
        #         'supplier': True,
        #         'category_id': [(6, 0, [category])]
        #     }
        #     partner_id = [partner_obj.create(cr, uid, item, context=context)]
        #     imported_supplier += 1
        #     # partner_obj.write(cr, uid, partner_id[0], item, context=context)
        #     _logger.info('%s supplier created: partner_id: %s', d, partner_id)
        # ########################################################################################
        #
        # ########################################################################################
        # category = self._get_or_create_category(cr, uid, '供应商')
        #
        # imported_supplier = 0
        # customers = set([x[2] for x in data])
        # for d in customers:
        #     partner_ids = partner_obj.search(cr, uid, [('name', 'in', [d])], context=context)
        #     if len(partner_ids) != 0 or len(d) == 0:
        #         _logger.info('customers %s is already created. partner_ids: %s', d, partner_ids)
        #         continue
        #
        #     item = {
        #         'customer': True,
        #         'name': d,
        #         'supplier': True,
        #         'category_id': [(6, 0, [category])]
        #     }
        #     partner_id = [partner_obj.create(cr, uid, item, context=context)]
        #     imported_supplier += 1
        #     # partner_obj.write(cr, uid, partner_id[0], item, context=context)
        #     _logger.info('%s supplier created: partner_id: %s', d, partner_id)
        # ########################################################################################
        #
        # product_obj = self.pool.get('product.product')
        #
        # imported_supplier = 0
        # customers = set([x[1] for x in data])
        # for d in customers:
        #     product_ids = product_obj.search(cr, uid, [('name', 'in', [d])], context=context)
        #     if len(product_ids) != 0:
        #         _logger.info('product %s is already created. product_ids: %s', d, product_ids)
        #         continue
        #
        #     item = {
        #         'name': d,
        #     }
        #     product_id = [product_obj.create(cr, uid, item, context=context)]
        #     imported_supplier += 1
        #     # partner_obj.write(cr, uid, partner_id[0], item, context=context)
        #     _logger.info('%s product created: product_id: %s', d, product_id)
        #####################################################################################################
        # Create purchase orders.

        for item in items:
            self.create_po(cr, uid, item, context=context)

        #####################################################################################################
        #####################################################################################################

        return True

    def _get_or_create_category(self, cr, uid, name, context=None):
        categories = self.pool.get('res.partner.category')

        category = categories.search(cr, uid, [('name', 'in', [name])])
        if len(category) == 0:
            category = [categories.create(cr, uid, {'name': name}, context=context)]

        return category[0]

    def _create_po_product(self, cr, uid, vals, item, context=None):
        purchase_obj = self.pool['purchase.order']
        # partner_obj = self.pool.get('res.partner')
        # product_obj = self.pool.get('product.product')

        if len(item['库房']) == 0:
            return False

        pl = self._get_picking_location(cr, uid, item['库房'], context=context)

        # 货物单
        # location_ids = location_obj.search(cr, uid, [('name', 'in', [item['库房']])], context=context)
        # if len(location_ids) == 0:
        #     _logger.info('supplier %s is not found. partner_ids: %s', item['库房'], location_ids)
        #     return False

        partner_ids = self._get_or_create_partner(cr, uid, {'name': item['供应商'],
                                                            'category': '供应商',
                                                            'customer': True}, context=context)

        # partner_ids = partner_obj.search(cr, uid, [('name', 'in', [item['供应商']])], context=context)
        # if len(partner_ids) == 0:
        #     _logger.info('supplier %s is not found. partner_ids: %s', item['供应商'], partner_ids)
        #     return False

        # product_ids = product_obj.search(cr, uid, [('name', 'in', [item['煤品种']])], context=context)
        # if len(product_ids) == 0:
        #     _logger.info('product %s is not found. product_ids: %s', item['煤品种'], product_ids)
        #     return False

        product_ids = self._get_or_create_product(cr, uid, {'name': item['煤品种']}, context=context)

        po_item_name = vals['name']
        vals['name'] = '/'
        vals['date_order'] = time.strftime('%Y-%m-%d %H:%M:%S')
        vals['picking_type_id'] = pl['picking_type_id']
        vals['location_id'] = pl['location_id']
        vals['partner_id'] = partner_ids[0]
        vals['order_line'][0][2]['product_id'] = product_ids[0]
        vals['order_line'][0][2]['date_planned'] = time.strftime('%Y-%m-%d')
        vals['order_line'][0][2]['price_unit'] = item['单价']
        vals['order_line'][0][2]['product_qty'] = item['净重']
        vals['order_line'][0][2]['name'] = item['车牌号']
        vals['notes'] = 'po_item_name:' + po_item_name

        po_id = purchase_obj.create(cr, uid, vals, context=context)

        purchase_obj.signal_workflow(cr, uid, [po_id], 'purchase_confirm')

        _logger.info('Purchase order from item %s create: %s.', item, po_id)

    def _create_po_shipping(self, cr, uid, vals, item, context=None):
        purchase_obj = self.pool['purchase.order']
        # partner_obj = self.pool.get('res.partner')
        # product_obj = self.pool.get('product.product')

        if len(item['库房']) == 0:
            return False

        pl = self._get_picking_location(cr, uid, item['库房'], context=context)

        # 运单
        # partner_ids = partner_obj.search(cr, uid, [('name', 'in', [item['车牌号']])], context=context)
        # if len(partner_ids) == 0:
        #     _logger.info('supplier %s is not found. partner_ids: %s', item['车牌号'], partner_ids)
        #     return False

        partner_ids = self._get_or_create_partner(cr, uid, {'name': item['车牌号'],
                                                            'mobile': int(item['电话']),
                                                            'categories': ['运输车辆', item['库房']],
                                                            'customer': True}, context=context)

        product_ids = self._get_or_create_product(cr, uid, {'name': '运输服务',
                                                            'type': 'service'}, context=context)

        # product_ids = product_obj.search(cr, uid, [('name', 'in', ['运输服务'])], context=context)
        # if len(product_ids) == 0:
        #     _logger.info('product %s is not found. product_ids: %s', '运输服务', product_ids)
        #     raise osv.except_osv(_('Not Found!'), _('没有服务产品: 运输服务'))
        #     # return False

        vals['name'] = '/'
        vals['date_order'] = time.strftime('%Y-%m-%d %H:%M:%S')
        vals['picking_type_id'] = pl['picking_type_id']
        vals['location_id'] = pl['location_id']
        vals['partner_id'] = partner_ids[0]
        vals['order_line'][0][2]['product_id'] = product_ids[0]
        vals['order_line'][0][2]['date_planned'] = item['日期']
        vals['order_line'][0][2]['price_unit'] = item['运费单价']
        vals['order_line'][0][2]['product_qty'] = item['净重']
        vals['order_line'][0][2]['name'] = '运输服务'
        vals['notes'] = False

        po_id = purchase_obj.create(cr, uid, vals, context=context)
        # purchase_obj.wkf_confirm_order(cr, uid, [po_id], context=context)
        # purchase_obj.wkf_approve_order(cr, uid, [po_id], context=context)
        # purchase_obj.picking_done(cr, uid, [po_id], context=context)
        # purchase_obj.action_invoice_create(cr, uid, [po_id], context=context)

        purchase_obj.signal_workflow(cr, uid, [po_id], 'purchase_confirm')

        _logger.info('Purchase order from item %s create: %s.', item, po_id)

    def create_po(self, cr, uid, item, context=None):
        company = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id

        journal_obj = self.pool.get('account.journal')
        journal_ids = journal_obj.search(cr, uid, [('type', '=', 'purchase'),
                                                   ('company_id', '=', company.id)], limit=1)

        if len(journal_ids) == 0:
            raise osv.except_osv(_('Not Found!'), _('订单导入失败，无法找到可用journal: journal_ids'))

        vals = {
            'origin': False,
            'dest_address_id': False,
            'date_order': '2016-07-06 09:52:37',
            'minimum_planned_date': False,
            'picking_type_id': 11,
            'location_id': 25,
            'notes': False,
            'order_line': [[0, False, {'product_id': 5,
                                       'product_uom': 1,
                                       'date_planned': '2016-07-06',
                                       'price_unit': 260,
                                       'taxes_id': [[6, False, []]],
                                       'product_qty': 56,
                                       'account_analytic_id': False,
                                       'name': u'\u7c89\u7164'}]],
            'journal_id': journal_ids[0],
            'company_id': company.id,
            'currency_id': 8,
            'invoice_method': 'order',
            'payment_term_id': False,
            'fiscal_position': False,
            'incoterm_id': False,
            'bid_validity': False,
            'message_follower_ids': False,
            'pricelist_id': 2,
            'partner_ref': False,
            'partner_id': 609,
            'message_ids': False
        }

        self._create_po_shipping(cr, uid, vals, item, context=context)
        self._create_po_product(cr, uid, vals, item, context=context)

        # _logger.info('Purchase order from item %s create: %s.', item, po_id)

        return True

    def _read_csv(self, record, options):
        """ Returns a CSV-parsed iterator of all empty lines in the file

        :throws csv.Error: if an error is detected during CSV parsing
        :throws UnicodeDecodeError: if ``options.encoding`` is incorrect
        """
        csv_iterator = csv.reader(
            StringIO(record.file),
            quotechar=str(options['quoting']),
            delimiter=str(options['separator']))

        def nonempty(row):
            return any(x for x in row if x.strip())

        csv_nonempty = itertools.ifilter(nonempty, csv_iterator)
        # TODO: guess encoding with chardet? Or https://github.com/aadsm/jschardet
        encoding = options.get('encoding', 'utf-8')

        return itertools.imap(
            lambda row: [item.decode(encoding) for item in row],
            csv_nonempty)

    def _convert_import_data(self, record, fields, options, context=None):
        """ Extracts the input browse_record and fields list (with
        ``False``-y placeholders for fields to *not* import) into a
        format Model.import_data can use: a fields list without holes
        and the precisely matching data matrix

        :param browse_record record:
        :param list(str|bool): fields
        :returns: (data, fields)
        :rtype: (list(list(str)), list(str))
        :raises ValueError: in case the import data could not be converted
        """
        # Get indices for non-empty fields
        indices = [index for index, field in enumerate(fields) if field]
        if not indices:
            raise ValueError(_("You must configure at least one field to import"))
        # If only one index, itemgetter will return an atom rather
        # than a 1-tuple
        if len(indices) == 1:
            mapper = lambda row: [row[indices[0]]]
        else:
            mapper = operator.itemgetter(*indices)
        # Get only list of actually imported fields
        import_fields = filter(None, fields)

        rows_to_import = self._read_csv(record, options)
        if options.get('headers'):
            rows_to_import = itertools.islice(rows_to_import, 1, None)
        data = [
            row for row in itertools.imap(mapper, rows_to_import)
            # don't try inserting completely empty rows (e.g. from
            # filtering out o2m fields)
            if any(row)
            ]

        return data, import_fields

    def get_fields(self, cr, uid, model, context=None, depth=FIELDS_RECURSION_LIMIT):
        """ Recursively get fields for the provided model (through
        fields_get) and filter them according to importability

        The output format is a list of ``Field``, with ``Field``
        defined as:

        .. class:: Field

            .. attribute:: id (str)

                A non-unique identifier for the field, used to compute
                the span of the ``required`` attribute: if multiple
                ``required`` fields have the same id, only one of them
                is necessary.

            .. attribute:: name (str)

                The field's logical (Odoo) name within the scope of
                its parent.

            .. attribute:: string (str)

                The field's human-readable name (``@string``)

            .. attribute:: required (bool)

                Whether the field is marked as required in the
                model. Clients must provide non-empty import values
                for all required fields or the import will error out.

            .. attribute:: fields (list(Field))

                The current field's subfields. The database and
                external identifiers for m2o and m2m fields; a
                filtered and transformed fields_get for o2m fields (to
                a variable depth defined by ``depth``).

                Fields with no sub-fields will have an empty list of
                sub-fields.

        :param str model: name of the model to get fields form
        :param int landing: depth of recursion into o2m fields
        """
        model_obj = self.pool[model]
        fields = [{
            'id': 'id',
            'name': 'id',
            'string': _("External ID"),
            'required': False,
            'fields': [],
        }]
        fields_got = model_obj.fields_get(cr, uid, context=context)
        blacklist = orm.MAGIC_COLUMNS + [model_obj.CONCURRENCY_CHECK_FIELD]
        for name, field in fields_got.iteritems():
            if name in blacklist:
                continue
            # an empty string means the field is deprecated, @deprecated must
            # be absent or False to mean not-deprecated
            if field.get('deprecated', False) is not False:
                continue
            if field.get('readonly'):
                states = field.get('states')
                if not states:
                    continue
                # states = {state: [(attr, value), (attr2, value2)], state2:...}
                if not any(attr == 'readonly' and value is False
                           for attr, value in itertools.chain.from_iterable(
                    states.itervalues())):
                    continue

            f = {
                'id': name,
                'name': name,
                'string': field['string'],
                # Y U NO ALWAYS HAS REQUIRED
                'required': bool(field.get('required')),
                'fields': [],
            }

            if field['type'] in ('many2many', 'many2one'):
                f['fields'] = [
                    dict(f, name='id', string=_("External ID")),
                    dict(f, name='.id', string=_("Database ID")),
                ]
            elif field['type'] == 'one2many' and depth:
                f['fields'] = self.get_fields(
                    cr, uid, field['relation'], context=context, depth=depth - 1)
                if self.pool['res.users'].has_group(cr, uid, 'base.group_no_one'):
                    f['fields'].append(
                        {'id': '.id', 'name': '.id', 'string': _("Database ID"), 'required': False, 'fields': []})

            fields.append(f)

        # TODO: cache on model?
        return fields

    def _match_headers(self, rows, fields, options):
        """ Attempts to match the imported model's fields to the
        titles of the parsed CSV file, if the file is supposed to have
        headers.

        Will consume the first line of the ``rows`` iterator.

        Returns a pair of (None, None) if headers were not requested
        or the list of headers and a dict mapping cell indices
        to key paths in the ``fields`` tree

        :param Iterator rows:
        :param dict fields:
        :param dict options:
        :rtype: (None, None) | (list(str), dict(int: list(str)))
        """
        if not options.get('headers'):
            return None, None

        headers = next(rows)
        return headers, dict(
            (index, [field['name'] for field in self._match_header(header, fields, options)] or None)
            for index, header in enumerate(headers)
        )

    def _match_header(self, header, fields, options):
        """ Attempts to match a given header to a field of the
        imported model.

        :param str header: header name from the CSV file
        :param fields:
        :param dict options:
        :returns: an empty list if the header couldn't be matched, or
                  all the fields to traverse
        :rtype: list(Field)
        """
        string_match = None
        for field in fields:
            # FIXME: should match all translations & original
            # TODO: use string distance (levenshtein? hamming?)
            if header.lower() == field['name'].lower():
                return [field]
            if header.lower() == field['string'].lower():
                # matching string are not reliable way because
                # strings have no unique constraint
                string_match = field
        if string_match:
            # this behavior is only applied if there is no matching field['name']
            return [string_match]

        if '/' not in header:
            return []

        # relational field path
        traversal = []
        subfields = fields
        # Iteratively dive into fields tree
        for section in header.split('/'):
            # Strip section in case spaces are added around '/' for
            # readability of paths
            match = self._match_header(section.strip(), subfields, options)
            # Any match failure, exit
            if not match: return []
            # prep subfields for next iteration within match[0]
            field = match[0]
            subfields = field['fields']
            traversal.append(field)
        return traversal
