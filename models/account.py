from openerp.osv import osv, fields
from openerp.tools.translate import _

_PAYMENT_METHOD_TYPE = [
	('cash', 'Cash'),
	('transfer', 'Transfer'),
	('receivable', 'EDC'),
	('giro', 'Giro')
]

class account_journal(osv.osv):
	_inherit = 'account.journal'
	_description = 'Modifikasi untuk me-link ke record master EDC'
	
	# FUNCTIONS -------------------------------------------------------------------------------------------------------------
	
	def _is_edc(self, cr, uid, ids, field_name, arg, context=None):
		res = {}
		for journal in self.browse(cr, uid, ids, context=context):
			res[journal.id] = len(journal.edc_machine_ids) > 0
		return res
	
	# COLUMNS ---------------------------------------------------------------------------------------------------------------
	
	_columns = {
		'edc_machine_ids': fields.one2many('account.journal.edc', 'journal_id'),
		'is_edc': fields.function(_is_edc, type='boolean', string='Is EDC')
	}

class account_voucher(osv.osv):
	_inherit = 'account.voucher'
	
	# COLUMNS ---------------------------------------------------------------------------------------------------------------
	
	_columns = {
		'payment_method_type': fields.selection(_PAYMENT_METHOD_TYPE, 'Payment Type', required=True),
		'sale_order_id': fields.many2one('sale.order', string='Sale Order'),
	}
	
	def _default_journal_id(self, cr, uid, context):
		journal_obj = self.pool.get('account.journal')
		journal_id = journal_obj.search(cr, uid, [('type', 'in', ['cash'])])
		return journal_id[0] if len(journal_id) > 0 else False
	
	_defaults = {
		'payment_method_type': 'cash',
		'journal_id': _default_journal_id,
	}
	
	def _onchange_payment_method_type(self, cr, uid, ids, payment_method_type, context=None):
		journal_obj = self.pool.get('account.journal')
		result = {}
		domain = {}
		value = {}
		if payment_method_type == 'cash':
			domain.update({'journal_id': [('type', 'in', ['cash'])]})
			journal_id = journal_obj.search(cr, uid, [('type', 'in', ['cash'])])
			value.update({'journal_id': journal_id[0] if len(journal_id) > 0 else False})
		elif payment_method_type in ['transfer', 'receivable', 'giro']:
			domain.update({'journal_id': [('type', 'in', ['bank'])]})
			journal_id = journal_obj.search(cr, uid, [('type', 'in', ['bank'])])
			value.update({'journal_id': journal_id[0] if len(journal_id) > 0 else False})
		
		if len(domain) > 0:
			result.update({'domain': domain})
		if len(value) > 0:
			result.update({'value': value})
		return result

	def proforma_voucher(self, cr, uid, ids, context=None):
		for account_voucher_data in self.browse(cr, uid, ids):
			new_context = context.copy() if context is not None else {}
			new_context.update({'payment_method_type': account_voucher_data.payment_method_type})
			new_context.update({'sale_order_id': account_voucher_data.sale_order_id.id})
			self.action_move_line_create(cr, uid, ids, context=new_context)
		return True

# ===========================================================================================================================

class account_journal_edc(osv.osv):
	_name = 'account.journal.edc'
	_description = 'Master data edc'
	
	# COLUMNS ---------------------------------------------------------------------------------------------------------------
	
	_columns = {
		'name': fields.char('Name', 100, required=True),
		'id_edc': fields.char('EDC ID'),
		'receivable_account_id': fields.many2one('account.account', 'Receivable Account',
			domain=[('type', '=', 'receivable')], required=True),
		'fee_account_id': fields.many2one('account.account', 'Card Fee Account',
			domain=[('type', '=', 'other')], required=True),
		'journal_id': fields.many2one('account.journal', 'Journal'),
		'debit_fee': fields.float('Debit Fee'),
		'credit_fee': fields.float('Credit Fee'),
	}
	
	# COLUMNS ---------------------------------------------------------------------------------------------------------------

	_defaults = {
		'debit_fee': 0,
		'credit_fee': 0,
		'receivable_account_id': lambda self, cr, uid, ctx=None: self.pool.get('ir.model.data')
			.get_object_reference(cr, uid, 'account', 'conf_a_recv')[1],
	}
	
	# CONSTRAINTS -----------------------------------------------------------------------------------------------------------

	_sql_constraints = [
		('unique_name', 'UNIQUE(journal_id, name)', _('The name of the EDC per journal must be unique!')),
		('unique_id_edc', 'UNIQUE(journal_id, id_edc)', _('The ID of the EDC per journal must be unique!')),
		('check_debit_fee', 'CHECK(debit_fee >= 0 AND debit_fee <= 100)', _('Debit fee must be between 0 and 100 percent!')),
		('check_credit_fee', 'CHECK(credit_fee >= 0 AND credit_fee <= 100)', _('Credit fee must be between 0 and 100 percent!')),
	]

class account_move_line(osv.osv):
	_inherit = 'account.move.line'
	_description = 'Modifikasi untuk menambah amount di SO'
	
	_columns = {
		'payment_method_type': fields.selection(_PAYMENT_METHOD_TYPE, 'Payment Type'),
	}
	
	def create(self, cr, uid, vals, context={}):
		new_id = super(account_move_line, self).create(cr, uid, vals, context=context)
		if context.get('payment_method_type', False) and context.get('sale_order_id', False):
			sale_order_obj = self.pool.get('sale.order')
			payment_method_type = context['payment_method_type']
			sale_order_id = context['sale_order_id']
			sale_order_data = sale_order_obj.browse(cr, uid, sale_order_id)
			if payment_method_type and vals.get('debit', False):
				if payment_method_type == 'cash':
					sale_order_obj.write(cr, uid, sale_order_id, {
						'payment_cash_amount': sale_order_data.payment_cash_amount + vals['debit']
					})
				elif payment_method_type == 'transfer':
					sale_order_obj.write(cr, uid, sale_order_id, {
						'payment_transfer_amount': sale_order_data.payment_transfer_amount + vals['debit']
					})
				elif payment_method_type == 'receivable':
					sale_order_obj.write(cr, uid, sale_order_id, {
						'payment_receivable_amount': sale_order_data.payment_receivable_amount + vals['debit']
					})
				elif payment_method_type == 'giro':
					sale_order_obj.write(cr, uid, sale_order_id, {
						'payment_giro_amount': sale_order_data.payment_giro_amount + vals['debit']
					})
		return new_id