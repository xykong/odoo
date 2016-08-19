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
