import openerp.addons.decimal_precision as dp
import logging
import time

from openerp import fields, api
from openerp.osv import fields, osv
from openerp.tools.translate import _

_logger = logging.getLogger(__name__)


class product_product(osv.Model):
    _name = 'product.product'
    _inherit = 'product.product'

    def _get_attribute_value(self, cr, uid, ids, name, context=None):
        result = dict.fromkeys(ids, False)
        for product in self.browse(cr, uid, ids, context=context):
            for variant_id in product.attribute_value_ids:
                if variant_id.attribute_id.name != name:
                    continue
                result[product.id] = variant_id.name
        return result


class product_template(osv.osv):
    _inherit = "product.template"

    def get_or_create_product(self, cr, uid, item, context=None):
        product_obj = self.pool.get('product.template')

        product_ids = product_obj.search(cr, uid, [('name', 'in', [item['name']])], context=context)
        if len(product_ids) != 0:
            # _logger.info('product %s is already created. product_ids: %s', item['name'], product_ids)
            return product_ids

        if 'type' not in item:
            item['type'] = 'consu'

        if 'sale_ok' not in item:
            item['sale_ok'] = 0

        if 'purchase_ok' not in item:
            item['purchase_ok'] = 0

        if 'uom_id' not in item:
            item['uom_id'] = 1
        if 'uom_po_id' not in item:
            item['uom_po_id'] = 1

        vals = {
            'name': item['name'],
            'type': item['type'],
            'categ_id': 1,
            'sale_ok': item['sale_ok'],
            'purchase_ok': item['purchase_ok'],
            'uom_id': item['uom_id'],
            'uom_po_id': item['uom_po_id'],
        }

        product_ids = [product_obj.create(cr, uid, vals, context=context)]
        _logger.info('%s product created: product_id: %s', item['name'], product_ids)

        # product = product_obj.browse(cr, uid, product_ids, context=context)

        return product_ids
