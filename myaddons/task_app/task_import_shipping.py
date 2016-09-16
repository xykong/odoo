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
import copy

from openerp.osv import orm
from openerp.tools.translate import _

FIELDS_RECURSION_LIMIT = 2
ERROR_PREVIEW_BYTES = 200
_logger = logging.getLogger(__name__)

from openerp.osv import osv, fields
import file_helper


class task_import_shipping(osv.osv_memory):
    """ Task Import Shipping Orders Class """

    _name = "task.import.shipping"
    # _description = "Task Import Shipping Orders"

    _columns = {
        'binary_field': fields.binary('Your binary field', required=True),
        'filename': fields.char('Filename'),
    }

    def create_po_ocean_shipping(self, cr, uid, vals, item, context=None):

        if len(item['目的港']) == 0:
            return False

        warehouse_obj = self.pool.get('stock.warehouse')

        pl = warehouse_obj.get_picking_location(cr, uid, item['目的港'], context=context)

        # 运单

        partner_obj = self.pool.get('res.partner')
        partner_ids = partner_obj.get_or_create_partner(cr, uid, {'name': item['海运'],
                                                                  # 'mobile': int(item['电话']),
                                                                  'categories': ['海运', item['目的港']],
                                                                  'supplier': True}, context=context)

        product_obj = self.pool.get('product.template')
        product_ids = product_obj.get_or_create_product(cr, uid, {'name': '海运服务', 'type': 'service'}, context=context)

        # partner_ids = self._get_or_create_partner(cr, uid, {'name': item['供应商'],
        #                                                     'category': '供应商',
        #                                                     'customer': True}, context=context)

        product_ids2 = product_obj.get_or_create_product(cr, uid, {'name': item['煤品种'],
                                                                   'purchase_ok': 1,
                                                                   'uom_id': 7,
                                                                   'uom_po_id': 7}, context=context)

        vals['name'] = '/'
        vals['date_order'] = time.strftime('%Y-%m-%d %H:%M:%S')
        vals['picking_type_id'] = pl['picking_type_id']
        vals['location_id'] = pl['location_id']
        vals['partner_id'] = partner_ids[0]
        vals['order_line'][0][2]['product_uom'] = 1
        vals['order_line'][0][2]['product_id'] = product_ids[0]
        vals['order_line'][0][2]['date_planned'] = item['日期']
        vals['order_line'][0][2]['price_unit'] = item['海运费']
        vals['order_line'][0][2]['product_qty'] = 1
        vals['order_line'][0][2]['name'] = item['箱号']
        vals['order_line'].append(copy.deepcopy(vals['order_line'][0]))
        vals['order_line'][1][2]['product_uom'] = 7
        vals['order_line'][1][2]['product_id'] = product_ids2[0]
        vals['order_line'][1][2]['date_planned'] = time.strftime('%Y-%m-%d')
        vals['order_line'][1][2]['price_unit'] = 0
        vals['order_line'][1][2]['product_qty'] = item['净重']
        vals['order_line'][1][2]['name'] = item['箱号']
        vals['notes'] = u'箱号: %s\n铅封号: %s\n航次: %s\n%s' % (item['箱号'], item['铅封号'], item['航次'], item['备注'])

        purchase_obj = self.pool['purchase.order']
        po_id = purchase_obj.create(cr, uid, vals, context=context)
        # purchase_obj.wkf_confirm_order(cr, uid, [po_id], context=context)
        # purchase_obj.wkf_approve_order(cr, uid, [po_id], context=context)
        # purchase_obj.picking_done(cr, uid, [po_id], context=context)
        # purchase_obj.action_invoice_create(cr, uid, [po_id], context=context)

        purchase_obj.signal_workflow(cr, uid, [po_id], 'purchase_confirm')

        purchase_obj = self.pool['purchase.order']
        po = purchase_obj.browse(cr, uid, po_id, context=context)

        # move_obj = self.pool.get('stock.move')
        # move_id = move_obj.search(cr, uid, [('origin', '=', picking.origin)])
        # move = move_obj.browse(cr, uid, move_id, context=context)

        pl_source = warehouse_obj.get_picking_location(cr, uid, item['场地'], context=context)
        po.picking_ids.location_id = pl_source['location_id']
        _logger.info('Purchase order from item %s create: %s.', item, po_id)

    def create_po_trailer(self, cr, uid, vals, item, context=None):

        if len(item['目的港']) == 0:
            return False

        warehouse_obj = self.pool.get('stock.warehouse')

        pl = warehouse_obj.get_picking_location(cr, uid, item['目的港'], context=context)

        # 运单

        partner_obj = self.pool.get('res.partner')
        partner_ids = partner_obj.get_or_create_partner(cr, uid, {'name': item['拖运'],
                                                                  # 'mobile': int(item['电话']),
                                                                  'categories': ['拖运', item['目的港']],
                                                                  'supplier': True}, context=context)

        product_obj = self.pool.get('product.template')
        product_ids = product_obj.get_or_create_product(cr, uid, {'name': '拖运服务', 'type': 'service'}, context=context)

        vals['name'] = '/'
        vals['date_order'] = time.strftime('%Y-%m-%d %H:%M:%S')
        vals['picking_type_id'] = pl['picking_type_id']
        vals['location_id'] = pl['location_id']
        vals['partner_id'] = partner_ids[0]
        vals['order_line'][0][2]['product_uom'] = 1
        vals['order_line'][0][2]['product_id'] = product_ids[0]
        vals['order_line'][0][2]['date_planned'] = item['日期']
        vals['order_line'][0][2]['price_unit'] = item['拖车费']
        vals['order_line'][0][2]['product_qty'] = 1
        vals['order_line'][0][2]['name'] = item['箱号']
        vals['notes'] = u'箱号: %s\n铅封号: %s\n航次: %s\n%s' % (item['箱号'], item['铅封号'], item['航次'], item['备注'])

        purchase_obj = self.pool['purchase.order']
        po_id = purchase_obj.create(cr, uid, vals, context=context)
        # purchase_obj.wkf_confirm_order(cr, uid, [po_id], context=context)
        # purchase_obj.wkf_approve_order(cr, uid, [po_id], context=context)
        # purchase_obj.picking_done(cr, uid, [po_id], context=context)
        # purchase_obj.action_invoice_create(cr, uid, [po_id], context=context)

        purchase_obj.signal_workflow(cr, uid, [po_id], 'purchase_confirm')

        # purchase_obj = self.pool['purchase.order']
        # po = purchase_obj.browse(cr, uid, po_id, context=context)

        # move_obj = self.pool.get('stock.move')
        # move_id = move_obj.search(cr, uid, [('origin', '=', picking.origin)])
        # move = move_obj.browse(cr, uid, move_id, context=context)

        # pl_source = warehouse_obj.get_picking_location(cr, uid, item['场地'], context=context)
        # po.picking_ids.location_id = pl_source['location_id']
        _logger.info('Purchase order from item %s create: %s.', item, po_id)

    def create_so(self, cr, uid, vals, item, context=None):

        vals = {'origin': False,
                'incoterm': False,
                'date_order': '2016-09-16 05:10:35',
                'user_id': 1,
                'partner_shipping_id': 17,
                'order_line': [[0, False, {'product_uos_qty': 10,
                                           'product_id': 3,
                                           'product_uom': 7,
                                           'route_id': False,
                                           'price_unit': 1,
                                           'product_uom_qty': 10,
                                           'delay': 7,
                                           'product_uos': False,
                                           'th_weight': 0,
                                           'product_packaging': False,
                                           'discount': 0,
                                           'tax_id': [[6, False, []]],
                                           'name': u'\u5e93\u623fA.\u4e09\u516b (500,300)'}]],
                'picking_policy': 'one',
                'order_policy': 'picking',
                'payment_term': False,
                'section_id': False,
                'warehouse_id': 3,
                'note': False,
                'message_follower_ids': False,
                'fiscal_position': False,
                'client_order_ref': False,
                'partner_invoice_id': 17,
                'pricelist_id': 1,
                'project_id': False,
                'partner_id': 17,
                'message_ids': False}

        warehouse_obj = self.pool.get('stock.warehouse')
        pl = warehouse_obj.get_picking_location(cr, uid, item['目的港'], context=context)

        partner_obj = self.pool.get('res.partner')
        partner_ids = partner_obj.get_or_create_partner(cr, uid, {'name': item['客户'],
                                                                  # 'mobile': int(item['电话']),
                                                                  'categories': ['客户', item['目的港']],
                                                                  'customer': True}, context=context)

        product_obj = self.pool.get('product.template')
        product_ids = product_obj.get_or_create_product(cr, uid, {'name': item['煤品种'],
                                                                  'purchase_ok': 1,
                                                                  'uom_id': 7,
                                                                  'uom_po_id': 7}, context=context)

        vals['name'] = '/'
        vals['date_order'] = time.strftime('%Y-%m-%d %H:%M:%S')
        vals['warehouse_id'] = pl['warehouse_id']
        vals['partner_shipping_id'] = partner_ids[0]
        vals['partner_invoice_id'] = partner_ids[0]
        vals['partner_id'] = partner_ids[0]
        vals['order_line'][0][2]['product_uos_qty'] = item['净重']
        vals['order_line'][0][2]['product_uom_qty'] = item['净重']
        vals['order_line'][0][2]['product_id'] = product_ids[0]
        vals['order_line'][0][2]['price_unit'] = item['销售价格']
        vals['order_line'][0][2]['name'] = item['箱号']
        vals['notes'] = u'箱号: %s\n铅封号: %s\n航次: %s\n%s' % (item['箱号'], item['铅封号'], item['航次'], item['备注'])

        sale_obj = self.pool['sale.order']
        so_id = sale_obj.create(cr, uid, vals, context=context)

        sale_obj.action_button_confirm(cr, uid, [so_id], context=None)

        _logger.info('Sale order from item %s create: %s.', item, so_id)

    def do_import_shipping(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        f = file_helper.file_helper()

        this = self.browse(cr, uid, ids[0])
        (record,) = self.browse(cr, uid, [id], context=context)

        require_fields = [
            '日期',
            '煤品种',
            '海运',
            '拖运',
            '箱号',
            '海运费',
            '拖车费',
            '净重',
            '场地',
            '客户',
            '销售价格',
            '铅封号',
            '目的港',
            '航次',
            '备注',
        ]

        items = f._retrieve_items(this.binary_field, record, require_fields)

        _logger.info('items: %s', items)

        ###########################################################################################
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
        ###########################################################################################

        for item in items:
            _logger.info('shipping item: %s', item)
            self.create_po_ocean_shipping(cr, uid, copy.deepcopy(vals), item, context=context)
            self.create_po_trailer(cr, uid, copy.deepcopy(vals), item, context=context)
            self.create_so(cr, uid, copy.deepcopy(vals), item, context=context)
            # return True

        return True
