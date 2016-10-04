# -*- coding: utf-8 -*-

from openerp.osv import osv
from openerp.tools.translate import _


# ----------------------------------------------------------
# Stock Warehouse
# ----------------------------------------------------------
class stock_warehouse(osv.osv):
    _inherit = 'stock.warehouse'

    def get_picking_location(self, cr, uid, name, context=None):
        company = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id
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
            'warehouse_id': wh.id,
            'picking_type_id': wh.in_type_id.id,
            'location_id': wh.lot_stock_id.id
        }
