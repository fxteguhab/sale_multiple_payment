# -*- coding: utf-8 -*-
# noinspection PyStatementEffect
{
    'name': "Sale Multiple Payment",

    'summary': """
        Multiple payment method for sale orders.
    """,

    'description': """
        Multiple payment method for sale orders.
    """,

    'author': "Nibble Softworks",
    'website': "http://www.nibblesoftworks.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'account'],

    # always loaded
    'data': [
        'data/sale_data.xml',
        'views/sale_view.xml',
        'views/account_view.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
    ],
}
