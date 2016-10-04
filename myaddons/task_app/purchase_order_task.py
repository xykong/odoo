# -*- coding: utf-8 -*-
import logging

from openerp import models

_logger = logging.getLogger(__name__)


class purchase_order_task(models.Model):
    _inherit = 'purchase.order'
    _name = 'purchase.order'
