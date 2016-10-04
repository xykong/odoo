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

import logging
import time
import file_helper

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from openerp.tools.translate import _
from openerp import SUPERUSER_ID

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

        f = file_helper.file_helper()

        this = self.browse(cr, uid, ids[0])
        (record,) = self.browse(cr, uid, [id], context=context)

        require_fields = ['日期', '煤品种', '供应商', '车牌号', '电话', '运费单价', '净重', '单价', '库房', '客户名']

        items = f.retrieve_items(this.binary_field, record, require_fields)

        # _logger.info('items: %s', items)

        if this.combine_names:
            for item in items:
                item['煤品种'] = item['库房'] + '.' + item['煤品种']

        for item in items:
            self.create_po(cr, uid, item, context=context)

        return True

    def _create_po_product(self, cr, uid, vals, item, context=None):

        if len(item['库房']) == 0:
            return False

        warehouse_obj = self.pool.get('stock.warehouse')
        pl = warehouse_obj.get_picking_location(cr, uid, item['库房'], context=context)

        # 货物单
        partner_obj = self.pool.get('res.partner')
        partner_ids = partner_obj.get_or_create_partner(cr, SUPERUSER_ID, {'name': item['供应商'],
                                                                           'category': ['供应商', '煤炭'],
                                                                           'supplier': True}, context=context)

        product_obj = self.pool.get('product.template')
        product_ids = product_obj.get_or_create_product(cr, SUPERUSER_ID, {'name': item['煤品种'],
                                                                           'sale_ok': 1,
                                                                           'purchase_ok': 1,
                                                                           'uom_id': 7,
                                                                           'uom_po_id': 7}, context=context)

        po_item_name = vals['name']
        vals['name'] = '/'
        vals['date_order'] = time.strftime('%Y-%m-%d %H:%M:%S')
        vals['picking_type_id'] = pl['picking_type_id']
        vals['location_id'] = pl['location_id']
        vals['partner_id'] = partner_ids[0]
        vals['order_line'][0][2]['product_uom'] = 7
        vals['order_line'][0][2]['product_id'] = product_ids[0]
        vals['order_line'][0][2]['date_planned'] = time.strftime('%Y-%m-%d')
        vals['order_line'][0][2]['price_unit'] = item['单价']
        vals['order_line'][0][2]['product_qty'] = item['净重']
        vals['order_line'][0][2]['name'] = item['车牌号']
        vals['notes'] = 'po_item_name:' + po_item_name

        purchase_obj = self.pool['purchase.order']
        po_id = purchase_obj.create(cr, uid, vals, context=context)

        purchase_obj.signal_workflow(cr, uid, [po_id], 'purchase_confirm')

        _logger.info('Purchase order from item %s create: %s.', item, po_id)

    def _create_po_shipping(self, cr, uid, vals, item, context=None):

        if len(item['库房']) == 0:
            return False

        warehouse_obj = self.pool.get('stock.warehouse')
        pl = warehouse_obj.get_picking_location(cr, uid, item['库房'], context=context)

        # 运单

        partner_obj = self.pool.get('res.partner')
        partner_ids = partner_obj.get_or_create_partner(cr, SUPERUSER_ID, {'name': item['车牌号'],
                                                                           'mobile': int(item['电话']),
                                                                           'categories': ['运输车辆', item['库房']],
                                                                           'supplier': True}, context=context)

        product_obj = self.pool.get('product.template')
        product_ids = product_obj.get_or_create_product(cr, SUPERUSER_ID, {'name': '运输服务', 'type': 'service'},
                                                        context=context)

        vals['name'] = '/'
        vals['date_order'] = time.strftime('%Y-%m-%d %H:%M:%S')
        vals['picking_type_id'] = pl['picking_type_id']
        vals['location_id'] = pl['location_id']
        vals['partner_id'] = partner_ids[0]
        vals['order_line'][0][2]['product_uom'] = 1
        vals['order_line'][0][2]['product_id'] = product_ids[0]
        vals['order_line'][0][2]['date_planned'] = item['日期']
        vals['order_line'][0][2]['price_unit'] = item['运费单价']
        vals['order_line'][0][2]['product_qty'] = item['净重']
        vals['order_line'][0][2]['name'] = '运输服务'
        vals['notes'] = False

        purchase_obj = self.pool['purchase.order']
        po_id = purchase_obj.create(cr, uid, vals, context=context)
        # purchase_obj.wkf_confirm_order(cr, uid, [po_id], context=context)
        # purchase_obj.wkf_approve_order(cr, uid, [po_id], context=context)
        # purchase_obj.picking_done(cr, uid, [po_id], context=context)
        # purchase_obj.action_invoice_create(cr, uid, [po_id], context=context)

        # purchase_obj.signal_workflow(cr, uid, [po_id], 'purchase_confirm')

        _logger.info('Purchase order from item %s create: %s.', item, po_id)

    def create_po(self, cr, uid, item, context=None):
        company = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id

        journal_obj = self.pool.get('account.journal')
        journal_ids = journal_obj.search(cr, uid, [('type', '=', 'purchase'),
                                                   ('company_id', '=', company.id)], limit=1)

        if len(journal_ids) == 0:
            raise osv.except_osv(_('Not Found!'), _('订单导入失败，无法找到可用journal, company_id: %d' % company))

        vals = {
            'origin': False,
            'dest_address_id': False,
            'date_order': '2016-07-06 09:52:37',
            'minimum_planned_date': False,
            'picking_type_id': 11,
            'location_id': 25,
            'notes': False,
            'order_line': [[0, False, {'product_id': 5,
                                       'product_uom': 7,
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
