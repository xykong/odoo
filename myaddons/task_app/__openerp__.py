# -*- coding: utf-8 -*-
{
    'name': "Task Import Application",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com
        """,

    'description': """
        Manage your personal Tasks with this module.
        """,

    'author': "Daniel Reis",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['account', 'purchase', 'stock', 'sale'],

    # always loaded
    'data': [
        'task_import.xml',
        'stock_view.xml'
        # 'purchase_order_task.xml',
    ],

    # only loaded in demonstration mode
    'demo': [
    ],

    'application': True,
}
