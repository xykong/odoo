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

from openerp.osv import fields, osv
from openerp.tools.translate import _

import logging

_logger = logging.getLogger(__name__)


class res_partner(osv.osv):
    _name = 'res.partner'
    _inherit = 'res.partner'

    def get_or_create_partner(self, cr, uid, item, context=None):
        partner_obj = self.pool.get('res.partner')

        categories = []
        if 'categories' in item:
            partner_category_obj = self.pool.get('res.partner.category')
            categories = [partner_category_obj.get_or_create_category(cr, uid, c) for c in item['categories']]
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
        if 'supplier' not in item:
            item['supplier'] = True

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


class res_partner_category(osv.osv):
    _inherit = 'res.partner.category'

    def get_or_create_category(self, cr, uid, name, context=None):
        categories = self.pool.get('res.partner.category')

        category = categories.search(cr, uid, [('name', 'in', [name])])
        if len(category) == 0:
            category = [categories.create(cr, uid, {'name': name}, context=context)]

        return category[0]
