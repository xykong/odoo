# -*- coding: utf-8 -*-
import openerp.addons.decimal_precision as dp
import logging
import time

from openerp import fields, api
from openerp.osv import fields, osv
from openerp.tools.translate import _

_logger = logging.getLogger(__name__)


class stock_move_tolerance(osv.osv_memory):
    _name = "stock.move.tolerance"
    _description = "Tolerance Products"

    _columns = {
        'product_id': fields.many2one('product.product', 'Product', required=True, select=True),
        'product_qty': fields.float('Quantity', digits_compute=dp.get_precision('Product Unit of Measure'),
                                    required=True),
        'product_uom': fields.many2one('product.uom', 'Product Unit of Measure', required=True),
        'location_id': fields.many2one('stock.location', 'Location', required=True),
        'restrict_lot_id': fields.many2one('stock.production.lot', 'Lot'),
        'tolerance_price': fields.float('Price'),
    }

    _defaults = {
        'location_id': lambda *x: False
    }

    def default_get(self, cr, uid, fields, context=None):
        """ Get default values
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param fields: List of fields for default value
        @param context: A standard dictionary
        @return: default values of fields
        """
        if context is None:
            context = {}

        move_ids = context['active_id']
        if context['active_model'] == 'stock.picking':
            picking = self.pool.get('stock.picking').browse(cr, uid, context['active_id'], context=context)
            move_ids = self.pool.get('stock.move').search(cr, uid, [('origin', '=', picking.origin)])

        res = super(stock_move_tolerance, self).default_get(cr, uid, fields, context=context)
        move = self.pool.get('stock.move').browse(cr, uid, move_ids, context=context)

        location_obj = self.pool.get('stock.location')
        scrap_location_id = location_obj.search(cr, uid, [('scrap_location', '=', True)])

        if 'product_id' in fields:
            res.update({'product_id': move.product_id.id})
        if 'product_uom' in fields:
            res.update({'product_uom': move.product_uom.id})
        if 'location_id' in fields:
            if scrap_location_id:
                res.update({'location_id': scrap_location_id[0]})
            else:
                res.update({'location_id': False})
        if 'product_qty' in fields:
            res.update({'product_qty': move.product_qty})
        return res

    def move_tolerance(self, cr, uid, ids, context=None):
        """ To move scrapped products
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: the ID or list of IDs if we want more than one
        @param context: A standard dictionary
        @return:
        """
        if context is None:
            context = {}

        move_obj = self.pool.get('stock.move')
        move_ids = context['active_id']
        if context['active_model'] == 'stock.picking':
            picking = self.pool.get('stock.picking').browse(cr, uid, context['active_id'], context=context)
            move_ids = self.pool.get('stock.move').search(cr, uid, [('origin', '=', picking.origin)])

        move = self.pool.get('stock.move').browse(cr, uid, move_ids, context=context)

        for data in self.browse(cr, uid, ids):
            move_obj.action_scrap(cr, uid, move_ids, move.product_qty - data.product_qty, data.location_id.id,
                                  restrict_lot_id=data.restrict_lot_id.id, context=context)

            purchase_obj = self.pool['purchase.order']

            purchase_product_ids = purchase_obj.search(cr, uid, [('name', 'in', [move.origin])], context=context)
            purchase_product = purchase_obj.browse(cr, uid, purchase_product_ids, context=context)

            shipping_name = ''
            for item in purchase_product.notes.split("\n"):
                if 'po_item_name:' in item:
                    shipping_name = item.strip().split(':')[1]

            purchase_shipping_ids = purchase_obj.search(cr, uid, [('name', 'in', [shipping_name])],
                                                        context=context)
            purchase_shipping = purchase_obj.browse(cr, uid, purchase_shipping_ids, context=context)

            if not purchase_shipping:
                raise osv.except_osv(_('Error!'), _(u'没有找到此单对应的运输单据, 因此无法计算实际运费。'))

            purchase_obj.action_cancel_draft(cr, uid, [purchase_shipping.id], context=context)

            task_import_obj = self.pool['task.import']
            po_line_obj = self.pool.get('purchase.order.line')
            tolerance = self.browse(cr, uid, ids, context=context)

            if move.product_qty > tolerance.product_qty:
                product_ids = task_import_obj._get_or_create_product(cr, uid, {'name': '实运差额', 'type': 'service'},
                                                                     context=context)
                product_obj = self.pool.get('product.template')
                product = product_obj.browse(cr, uid, product_ids, context=context)

                vals = {
                    'name': product.name,
                    'product_id': product.id,
                    'product_qty': - abs(move.product_qty - tolerance.product_qty),
                    'price_unit': purchase_shipping.order_line[0].price_unit,
                    'date_planned': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'product_uom': 1,
                    'taxes_id': [[6, False, []]],
                    'account_analytic_id': False,
                    'order_id': purchase_shipping.id,
                }
                po_line_id = po_line_obj.create(cr, uid, vals, context=context)
                purchase_shipping.write({'order_line': [(4, po_line_id)]})

            product_ids = task_import_obj._get_or_create_product(cr, uid, {'name': '涨吨差额', 'type': 'service'},
                                                                 context=context)
            product_obj = self.pool.get('product.template')
            product = product_obj.browse(cr, uid, product_ids, context=context)

            price_rise_att = tolerance.product_id._get_attribute_value(u'涨吨价格')
            if not price_rise_att[tolerance.product_id.id]:
                raise osv.except_osv(_('Error!'), _(u'产品 [%s] 没有定义属性: %s' % (tolerance.product_id.name, u'涨吨价格')))
            price_rise = float(price_rise_att[tolerance.product_id.id])

            vals = {
                'name': product.name,
                'product_id': product.id,
                'product_qty': - abs(move.product_qty - tolerance.product_qty),
                'price_unit': price_rise,
                'date_planned': time.strftime('%Y-%m-%d %H:%M:%S'),
                'product_uom': 1,
                'taxes_id': [[6, False, []]],
                'account_analytic_id': False,
                'order_id': purchase_shipping.id,
            }

            po_line_id = po_line_obj.create(cr, uid, vals, context=context)
            purchase_shipping.write({'order_line': [(4, po_line_id)]})

            product_ids = task_import_obj._get_or_create_product(cr, uid, {'name': '装卸费', 'type': 'service'},
                                                                 context=context)
            product_obj = self.pool.get('product.template')
            product = product_obj.browse(cr, uid, product_ids, context=context)

            loading_fee_att = tolerance.product_id._get_attribute_value(u'装卸费')
            if not loading_fee_att[tolerance.product_id.id]:
                raise osv.except_osv(_('Error!'), _(u'产品 [%s] 没有定义属性: %s' % (tolerance.product_id.name, u'装卸费')))
            loading_fee = float(loading_fee_att[tolerance.product_id.id])

            vals = {
                'name': product.name,
                'product_id': product.id,
                'product_qty': -1,
                'price_unit': loading_fee,
                'date_planned': time.strftime('%Y-%m-%d %H:%M:%S'),
                'product_uom': 1,
                'taxes_id': [[6, False, []]],
                'account_analytic_id': False,
                'order_id': purchase_shipping.id,
            }
            po_line_id = po_line_obj.create(cr, uid, vals, context=context)
            purchase_shipping.write({'order_line': [(4, po_line_id)]})

            purchase_obj.signal_workflow(cr, uid, [purchase_shipping.id], 'purchase_confirm')
            # purchase_obj.action_invoice_create(cr, uid, purchase_shipping.id, context=context)

            move_obj.action_done(cr, uid, move_ids, context=context)

        # if move.picking_id:
        #     return {
        #         'view_type': 'form',
        #         'view_mode': 'form',
        #         'res_model': 'stock.picking',
        #         'type': 'ir.actions.act_window',
        #         'res_id': move.picking_id.id,
        #         'context': context
        #     }
        return {'type': 'ir.actions.act_window_close'}

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        if self.product_id:
            _logger.info('product_id.id: %s', self.product_id.id)

        context = self.env.context

        if not context.get('active_id'):
            raise osv.except_osv(_('Error!'), _('产品数据错误，请刷新页面后重试。'))

        move_ids = context.get('active_id')
        if context['active_model'] == 'stock.picking':
            picking = self.pool.get('stock.picking').browse(self.env.cr, self.env.uid, context['active_id'],
                                                            context=context)
            move_ids = self.pool.get('stock.move').search(self.env.cr, self.env.uid, [('origin', '=', picking.origin)])

        move = self.pool.get('stock.move').browse(self.env.cr, self.env.uid, move_ids, context=context)

        if not move.picking_id:
            raise osv.except_osv(_('Error!'), _('产品数据错误，请刷新页面后重试。'))

        price_rise_att = self.product_id._get_attribute_value(u'涨吨价格')
        if not price_rise_att[self.product_id.id]:
            raise osv.except_osv(_('Error!'), _(u'产品 [%s] 没有定义属性: %s' % (self.product_id.name, u'涨吨价格')))
        price_rise = float(price_rise_att[self.product_id.id])

        loading_fee_att = self.product_id._get_attribute_value(u'装卸费')
        if not loading_fee_att[self.product_id.id]:
            raise osv.except_osv(_('Error!'), _(u'产品 [%s] 没有定义属性: %s' % (self.product_id.name, u'装卸费')))
        loading_fee = float(loading_fee_att[self.product_id.id])

        purchase_obj = self.pool['purchase.order']

        purchase_product_ids = purchase_obj.search(self.env.cr, self.env.uid, [('name', 'in', [move.origin])],
                                                   context=context)
        purchase_product = purchase_obj.browse(self.env.cr, self.env.uid, purchase_product_ids, context=context)

        shipping_name = ''
        for item in purchase_product.notes.split("\n"):
            if 'po_item_name:' in item:
                shipping_name = item.strip().split(':')[1]

        purchase_shipping_ids = purchase_obj.search(self.env.cr, self.env.uid, [('name', 'in', [shipping_name])],
                                                    context=context)
        purchase_shipping = purchase_obj.browse(self.env.cr, self.env.uid, purchase_shipping_ids, context=context)

        if not purchase_shipping:
            raise osv.except_osv(_('Error!'), _(u'没有找到此单对应的运输单据, 因此无法计算实际运费。'))

        self.tolerance_price = min(move.product_qty, self.product_qty) * purchase_shipping.order_line[
            0].price_unit - abs(
            move.product_qty - self.product_qty) * price_rise - loading_fee

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
