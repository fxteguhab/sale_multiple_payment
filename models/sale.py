from openerp import tools
from openerp.osv import osv, fields
from openerp.tools.translate import _

# ==========================================================================================================================

class sale_order(osv.osv):
	_inherit = 'sale.order'

	# COLUMNS ---------------------------------------------------------------------------------------------------------------

	def _amount_all_wrapper(self, cr, uid, ids, field_name, arg, context=None):
		""" Wrapper because of direct method passing as parameter for function fields """
		return self._amount_all(cr, uid, ids, field_name, arg, context=context)

	def _is_journal_edc(self, cr, uid, ids, field_name, arg, context=None):
		res = {}
		for sale_order in self.browse(cr, uid, ids, context=context):
			res[sale_order.id] = len(sale_order.payment_method_id.edc_machine_ids.ids) > 0
		return res

	def _card_fee_amount(self, cr, uid, ids, field_name, arg, context=None):
		res = {}
		for sale_order in self.browse(cr, uid, ids, context=context):
			res[sale_order.id] = sale_order.card_fee * sale_order.amount_total / 100
		return res

	_columns = {
		'payment_method_id': fields.many2one('account.journal', 'Payment Method'),
		'edc_id': fields.many2one('account.journal.edc', 'EDC'),
		'approval_code': fields.char('Approval Code'),
		'debit_or_credit': fields.selection([
			('debit','Debit'),
			('credit','Credit')
		], 'Card'),
		'card_fee': fields.float('Card Fee (%)'),
		'card_fee_amount': fields.float('Card Fee'),#fields.function(_amount_all_wrapper, type='float', string='Card Fee Amount', store=True, multi='sums'),
		'amount_total': fields.function(_amount_all_wrapper, type='float', string='Total Amount', store=True, multi='sums'),
		'is_journal_edc': fields.function(_is_journal_edc, type='boolean', string='Is Journal EDC'),
		'payment_transfer_amount': fields.float('Transfer Amount'),
		'payment_cash_amount': fields.float('Cash Amount'),
		'payment_receivable_amount': fields.float('EDC Amount'),
		'payment_giro_amount': fields.float('Giro Amount'),
		'payment_transfer_journal': fields.many2one('account.journal', 'Journal for Transfer Payment', domain=[('type','in',['cash','bank'])]),
		'payment_cash_journal': fields.many2one('account.journal', 'Journal for Cash Payment', domain=[('type','in',['cash','bank'])]),
		'payment_receivable_journal': fields.many2one('account.journal', 'Journal for EDC Payment', domain=[('type','in',['cash','bank'])]),
		'payment_giro_journal': fields.many2one('account.journal', 'Journal for Giro Payment', domain=[('type','in',['cash','bank'])]),
		'is_paid': fields.boolean('Paid ?'),
	}

	def _default_payment_method_id(self, cr, uid, context=None):
		journal_obj = self.pool.get('account.journal')
		result = False
		journal_ids = journal_obj.search(cr, uid, [('type', 'in', ['cash'])])
		if len(journal_ids) > 0:
			journals = journal_obj.browse(cr, uid, journal_ids)
			result = journals[0].id
		return result

	_defaults = {
		'payment_method_id': _default_payment_method_id,
		'is_paid' : True,
	}
	
	def create(self, cr, uid, vals, context={}):
		new_id = super(sale_order, self).create(cr, uid, vals, context)
		if vals.get('is_paid',True) and not vals.get('payment_cash_amount', False) and not vals.get('payment_transfer_amount', False) and \
				not vals.get('payment_receivable_amount', False) and not vals.get('payment_giro_amount', False):
			self.write(cr, uid, new_id, {
				'payment_cash_amount': self.browse(cr, uid, new_id, context=context).amount_total
			}, context=context)
		return new_id
	
	def  write(self, cr, uid, ids, vals, context=None):
		for sale in self.browse(cr, uid, ids):
		# Lakukan pengecekan apakah amount total berubah, amount total diketahui berubah ketika sudah dilakukan write
			old_amount_total = sale.amount_total
			super(sale_order, self).write(cr, uid, sale.id, vals, context)
			new_amount_total = sale.amount_total
			if old_amount_total != new_amount_total:
			# Jika berubah maka cek apakah user merubah salah 1 field payment, jika iya maka jangan update
				if vals.get('is_paid',True) and not vals.get('payment_cash_amount', False) and not vals.get('payment_transfer_amount', False) and \
						not vals.get('payment_receivable_amount', False) and not vals.get('payment_giro_amount', False):
					self.write(cr, uid, sale.id, {
						'payment_cash_amount': new_amount_total
					}, context=context)
		return True

	# CONSTRAINTS -----------------------------------------------------------------------------------------------------------

	_sql_constraints = [
		('card_fee_percentage', 'CHECK(card_fee >= 0 AND card_fee <= 100)', _('Card fee must be between 0 and 100 percent!')),
		('edc_approval_code_unique', 'unique (edc_id,approval_code)', _('The approval code must be unique per EDC!')),
	]

	# ONCHANGE --------------------------------------------------------------------------------------------------------------

	def onchange_card_fee(self, cr, uid, ids, card_fee, amount_total, context=None):
		return {'value': {'card_fee_amount': card_fee * amount_total / 100}}

	def onchange_payment_method_id(self, cr, uid, ids, payment_method_id, context=None):
		account_journal_obj = self.pool.get('account.journal')
		account_journal = account_journal_obj.browse(cr, uid, payment_method_id)
		return {
			'value': {
				'is_journal_edc': len(account_journal.edc_machine_ids.ids) > 0,
			},
			'domain': {
				'edc_id': [('id', 'in', account_journal.edc_machine_ids.ids)]
			}
		}

	def onchange_debit_or_credit(self, cr, uid, ids, edc_id, credit_or_debit, context=None):
		if edc_id and credit_or_debit:
			account_journal_edc_obj = self.pool.get('account.journal.edc')
			edc = account_journal_edc_obj.browse(cr, uid, edc_id)
			if credit_or_debit == 'credit':
				card_fee = edc.credit_fee
			elif credit_or_debit == 'debit':
				card_fee = edc.debit_fee
			else:
				card_fee = 0
			return {'value': {
				'card_fee': card_fee
			}}

	# WORKFLOWS -------------------------------------------------------------------------------------------------------------

	def action_additional_payment(self, cr, uid, ids, context=None):
		"""
		TODO Description
		"""
		if not ids: return []
		so = self.browse(cr, uid, ids[0], context=context)
		ir_model_data = self.pool.get('ir.model.data')
		payment_form_id = ir_model_data.get_object_reference(cr, uid, 'sale_multiple_payment',
			'sale_additional_payment_memory_form')[1]
		invoice_id = self.browse(cr, uid, ids, context)[0].invoice_ids[0]
		context = dict(context)
		context.update({
			'default_invoice_id': invoice_id.id,
			'default_amount_total': so.amount_total,
			'default_sale_order_id': so.id,
			'default_amount_residual' : invoice_id.residual,
		})
		return {
			'type': 'ir.actions.act_window',
			'name': _("Register Additional Payment"),
			'view_type': 'form',
			'view_mode': 'form',
			'res_model': 'sale.additional.payment.memory',
			'views': [(payment_form_id, 'form')],
			'view_id': payment_form_id,
			'target': 'new',
			'context': context,
		}
	
	def action_customer_pay(self, cr, uid, ids, context=None):
		if not ids: return []
		dummy, view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'account_voucher',
			'view_vendor_receipt_dialog_form')
		inv = self.browse(cr, uid, ids, context)[0].invoice_ids[0]
		return {
			'name':_("Pay Invoice"),
			'view_mode': 'form',
			'view_id': view_id,
			'view_type': 'form',
			'res_model': 'account.voucher',
			'type': 'ir.actions.act_window',
			'nodestroy': True,
			'target': 'new',
			'domain': '[]',
			'context': {
				'payment_expected_currency': inv.currency_id.id,
				'default_partner_id': self.pool.get('res.partner')._find_accounting_partner(inv.partner_id).id,
				'default_amount': inv.type in ('out_refund', 'in_refund') and -inv.residual or inv.residual,
				'default_reference': inv.name,
				'default_sale_order_id': ids[0] if len(ids)>0 else 0,
				'close_after_process': True,
				'invoice_type': inv.type,
				'invoice_id': inv.id,
				'default_type': inv.type in ('out_invoice','out_refund') and 'receipt' or 'payment',
				'type': inv.type in ('out_invoice','out_refund') and 'receipt' or 'payment'
			}
		}


	#def action_invoice_create(self, cr, uid, ids, grouped=False, states=None, date_invoice = False, context=None):
	#	res = super(sale_order, self).action_invoice_create(cr, uid, ids, grouped, states, date_invoice, context)
		# Make created invoice to open state

	#	return res
		# if states is None:
		# 	states = ['confirmed', 'done', 'exception']
		# res = False
		# invoices = {}
		# invoice_ids = []
		# invoice = self.pool.get('account.invoice')
		# obj_sale_order_line = self.pool.get('sale.order.line')
		# partner_currency = {}
		# # If date was specified, use it as date invoiced, usefull when invoices are generated this month and put the
		# # last day of the last month as invoice date
		# if date_invoice:
		# 	context = dict(context or {}, date_invoice=date_invoice)
		# for o in self.browse(cr, uid, ids, context=context):
		# 	currency_id = o.pricelist_id.currency_id.id
		# 	if (o.partner_id.id in partner_currency) and (partner_currency[o.partner_id.id] <> currency_id):
		# 		raise osv.except_osv(
		# 			_('Error!'),
		# 			_('You cannot group sales having different currencies for the same partner.'))
		#
		# 	partner_currency[o.partner_id.id] = currency_id
		# 	lines = []
		# 	for line in o.order_line:
		# 		if line.invoiced:
		# 			continue
		# 		elif (line.state in states):
		# 			lines.append(line.id)
		# 	created_lines = obj_sale_order_line.invoice_line_create(cr, uid, lines, context=context)
		# 	if created_lines:
		# 		invoices.setdefault(o.partner_invoice_id.id or o.partner_id.id, []).append((o, created_lines))
		# if not invoices:
		# 	for o in self.browse(cr, uid, ids, context=context):
		# 		for i in o.invoice_ids:
		# 			if i.state == 'draft':
		# 				return i.id
		# for val in invoices.values():
		# 	if grouped:
		# 		res = self._make_invoice(cr, uid, val[0][0], reduce(lambda x, y: x + y, [l for o, l in val], []), context=context)
		# 		invoice_ref = ''
		# 		origin_ref = ''
		# 		for o, l in val:
		# 			invoice_ref += (o.client_order_ref or o.name) + '|'
		# 			origin_ref += (o.origin or o.name) + '|'
		# 			self.write(cr, uid, [o.id], {'state': 'progress'})
		# 			cr.execute('insert into sale_order_invoice_rel (order_id,invoice_id) values (%s,%s)', (o.id, res))
		# 			self.invalidate_cache(cr, uid, ['invoice_ids'], [o.id], context=context)
		# 		#remove last '|' in invoice_ref
		# 		if len(invoice_ref) >= 1:
		# 			invoice_ref = invoice_ref[:-1]
		# 		if len(origin_ref) >= 1:
		# 			origin_ref = origin_ref[:-1]
		# 		invoice.write(cr, uid, [res], {'origin': origin_ref, 'name': invoice_ref})
		# 	else:
		# 		for order, il in val:
		# 			res = self._make_invoice(cr, uid, order, il, context=context)
		# 			invoice_ids.append(res)
		# 			self.write(cr, uid, [order.id], {'state': 'progress'})
		# 			cr.execute('insert into sale_order_invoice_rel (order_id,invoice_id) values (%s,%s)', (order.id, res))
		# 			self.invalidate_cache(cr, uid, ['invoice_ids'], [order.id], context=context)
		# return res

	def action_cash_sales(self, cr, uid, ids, context=None):
		acc_move_obj = self.pool.get('account.move')
		model, cash_sales_journal_id = self.pool['ir.model.data'].get_object_reference(
			cr, uid, 'sale_multiple_payment', 'sale_multiple_payment_journal_cash_sales_journal')
		journal_obj = self.pool.get('account.journal')
		sale_journal_data = journal_obj.browse(cr, uid, cash_sales_journal_id)
		line_id_vals = []
		for order in self.browse(cr, uid, ids, context):
			total_amount = 0
			for order_line in order.order_line:
				line_id_vals.append((0, False, {
					'name': order_line.product_id.name,
					'partner_id': order.partner_id.id,
				# ambil dari account default income buat product template dari product ini, atau (bila kosong) dari account default di kategorinya
					'account_id': order_line.product_id.product_tmpl_id.property_account_income and order_line.product_id.product_tmpl_id.property_account_income.id or order_line.product_id.product_tmpl_id.categ_id.property_account_income_categ.id,
					'credit': order_line.price_subtotal,
				}))
				total_amount += order_line.price_subtotal
		# tentukan account untuk debet
		# bila pakai edc, pakai default account si EDC nya
		# kalau bukan, pakai default debit account si payment journalnya
			if order.is_journal_edc:
				debit_account_id = order.edc_id.receivable_account_id.id
			else:
				debit_account_id = order.payment_method_id.default_debit_account_id.id
			line_id_vals.append((0, False, {
				'name': order.name,
				'partner_id': order.partner_id.id,
				'account_id': debit_account_id,
				'debit': total_amount + order.card_fee_amount,
			}))
		# kalau ada biaya terkait edc, masukkan juga jadi kolom credit
			if order.is_journal_edc and order.card_fee_amount > 0:
				line_id_vals.append((0, False, {
					'name': _('Card fee for order %s') % order.name,
					'partner_id': order.partner_id.id,
					'account_id': order.edc_id.fee_account_id.id,
					'credit': order.card_fee_amount,
				}))
		try:
			new_id = acc_move_obj.create(cr, uid, {
				'journal_id': cash_sales_journal_id,
				'ref': order.name,
				'line_id': line_id_vals,
			}, context)
			acc_move_obj.button_validate(cr, uid, [new_id], context=context)
		except:
			raise osv.except_osv(_('Sales Order Error'),_('Please set default income account either on the product master or product category master.'))
		pass

	def action_ship_create(self, cr, uid, ids, context=None):
		"""
		Force availability created pickings
		"""
		if context is None:
			context = {}
		result = super(sale_order, self).action_ship_create(cr, uid, ids, context)
		picking_obj = self.pool.get('stock.picking')
		pick_ids = []
		shipped_or_taken = False
		for so in self.browse(cr, uid, ids, context=context):
			pick_ids += [picking.id for picking in so.picking_ids]
			shipped_or_taken = so.shipped_or_taken
		context = context.copy()
		context.update({'shipped_or_taken': shipped_or_taken})
		picking_obj.force_assign(cr, uid, pick_ids, context)
		return result

	# OVERRIDES -------------------------------------------------------------------------------------------------------------

	def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
		res = super(sale_order, self)._amount_all(cr, uid, ids, field_name, arg, context)
		for order in self.browse(cr, uid, ids, context=context):
			res[order.id]['card_fee_amount'] = res[order.id]['amount_total'] * order.card_fee / 100
			res[order.id]['amount_total'] = res[order.id]['amount_total'] + res[order.id]['card_fee_amount']
		return res
	
	# FUNCTION -------------------------------------------------------------------------------------------------------------
    #
	# def reg_payment(self, cr, uid, ids, context=None):
	# 	if not ids: return []
	# 	dummy, view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'sale_multiple_payment', 'register_payment_sale_multiple_payment_dialog_form')
	#
	# 	return {
	# 		'name':_("Register Add Payment"),
	# 		'view_mode': 'form',
	# 		'view_id': view_id,
	# 		'view_type': 'form',
	# 		'res_model': 'sale.register.add.payment',
	# 		'type': 'ir.actions.act_window',
	# 		'nodestroy': True,
	# 		'target': 'new',
	# 		'domain': '[]',
	# 		'context': {
	#
	# 		}
	# 	}

# ==========================================================================================================================

class sale_edc_recap(osv.osv):
	_name = 'sale.edc.recap'
	_auto = False
	
	# COLUMNS ---------------------------------------------------------------------------------------------------------------
	
	_columns = {
		'sale_date': fields.date('Date'),
		'edc_id': fields.many2one('account.journal.edc', 'EDC'),
		'amount_debit': fields.float('Debit Amount'),
		'amount_credit': fields.float('Credit Amount'),
		'amount_total': fields.float('Total Amount'),
		'fee_debit': fields.float('Debit Fee'),
		'fee_credit': fields.float('Credit Fee'),
		'amount_nett_debit': fields.float('Debit Amount (Nett)'),
		'amount_nett_credit': fields.float('Credit Amount (Nett)'),
		'amount_nett_total': fields.float('Total Amount (Nett)')
	}
	
	# OVERRIDES -------------------------------------------------------------------------------------------------------------
	
	def init(self, cr):
		tools.sql.drop_view_if_exists(cr, 'sale_edc_recap')
		cr.execute('''
			CREATE OR REPLACE VIEW sale_edc_recap AS (
				SELECT
				  row_number()
				  OVER ()                                                             AS id,
				  CASE WHEN debit.sale_date IS NOT NULL
					THEN debit.sale_date
				  ELSE credit.sale_date END                                           AS sale_date,
				  CASE WHEN debit.edc_id IS NOT NULL
					THEN debit.edc_id
				  ELSE credit.edc_id END                                              AS edc_id,
				  coalesce(debit.amount_debit, 0)                                     AS amount_debit,
				  coalesce(credit.amount_credit, 0)                                   AS amount_credit,
				  coalesce(debit.amount_debit, 0) + coalesce(credit.amount_credit, 0) AS amount_total,
				  coalesce(debit.fee_debit, 0)                                        AS fee_debit,
				  coalesce(credit.fee_credit, 0)                                      AS fee_credit,
				  coalesce(debit.amount_debit, 0) + coalesce(debit.fee_debit, 0)      AS amount_nett_debit,
				  coalesce(credit.amount_credit, 0) + coalesce(credit.fee_credit, 0)  AS amount_nett_credit,
				  coalesce(debit.amount_debit, 0) + coalesce(debit.fee_debit, 0) + coalesce(credit.amount_credit, 0) +
				  coalesce(credit.fee_credit, 0)                                      AS amount_nett_total
				FROM
				  (
					SELECT
					  date_trunc('day', so.date_order)  AS sale_date,
					  edc.id                            AS edc_id,
					  COALESCE(SUM(amount_total), 0)    AS amount_debit,
					  COALESCE(SUM(card_fee_amount), 0) AS fee_debit
					FROM
					  sale_order so
					  LEFT JOIN account_journal_edc edc
						ON so.edc_id = edc.id
					WHERE
					  so.edc_id IS NOT NULL AND so.debit_or_credit = 'debit'
					GROUP BY
					  sale_date, edc.id) AS debit
				  FULL OUTER JOIN
				  (
					SELECT
					  date_trunc('day', so.date_order)  AS sale_date,
					  edc.id                            AS edc_id,
					  COALESCE(SUM(amount_total), 0)    AS amount_credit,
					  COALESCE(SUM(card_fee_amount), 0) AS fee_credit
					FROM
					  sale_order so
					  LEFT JOIN account_journal_edc edc
						ON so.edc_id = edc.id
					WHERE
					  so.edc_id IS NOT NULL AND so.debit_or_credit = 'credit'
					GROUP BY
					  sale_date, edc.id) AS credit
					ON debit.sale_date = credit.sale_date AND debit.edc_id = credit.edc_id
			)
		''')

class sale_additional_payment_memory(osv.osv_memory):
	_name = 'sale.additional.payment.memory'

	# COLUMNS -----------------------------------------------------------------------------------------------------------------------

	_columns = {
		'invoice_id': fields.many2one('account.invoice', 'Invoice'),
		'payment_method_id': fields.many2one('account.journal', 'Payment Method'),
		'sale_order_id': fields.many2one('sale.order', 'Sale Order'),
		'edc_id': fields.many2one('account.journal.edc', 'EDC'),
		'approval_code': fields.char('Approval Code'),
		'debit_or_credit': fields.selection([
			('debit','Debit'),
			('credit','Credit')
		], 'Card'),
		'card_fee': fields.float('Card Fee (%)'),
		'card_fee_amount': fields.float('Card Fee Amount'),
		'payment_transfer_amount': fields.float('Transfer Amount'),
		'payment_cash_amount': fields.float('Cash Amount'),
		'payment_receivable_amount': fields.float('EDC Amount'),
		'payment_giro_amount': fields.float('Giro Amount'),
		'amount_total': fields.float('Amount Total'),
		'amount_residual':fields.float('Balance'),
		'payment_transfer_journal': fields.many2one('account.journal', 'Journal for Transfer Payment', domain=[('type','in',['cash','bank'])]),
		'payment_cash_journal': fields.many2one('account.journal', 'Journal for Cash Payment', domain=[('type','in',['cash','bank'])]),
		'payment_receivable_journal': fields.many2one('account.journal', 'Journal for EDC Payment', domain=[('type','in',['cash','bank'])]),
		'payment_giro_journal': fields.many2one('account.journal', 'Journal for Giro Payment', domain=[('type','in',['cash','bank'])]),
	}


	def _default_payment_cash_journal(self, cr, uid, context={}):
		user_data = self.pool['res.users'].browse(cr, uid, uid)
		branch_id = user_data.branch_id.id
		branch_data = self.pool['tbvip.branch'].browse(cr,uid,branch_id)
		branch_employee = branch_data.employee_list
		default_journal_sales = None
		for employee in branch_employee:
			if employee.user_id.id == uid:
				default_journal_sales =  employee.default_journal_sales_override.id
		return default_journal_sales
		'''
		user_data = self.pool['res.users'].browse(cr, uid, uid)
		if user_data.default_journal_sales_override:
			return user_data.default_journal_sales_override.id
		else:
			if user_data.branch_id.default_journal_sales:
				return user_data.branch_id.default_journal_sales.id
			else:
				return None
		'''

	def _default_payment_receivable_journal(self, cr, uid, context={}):
		user_data = self.pool['res.users'].browse(cr, uid, uid)
		branch_id = user_data.branch_id.id
		branch_data = self.pool['tbvip.branch'].browse(cr,uid,branch_id)
		journal_id = branch_data.default_journal_sales_bank.id
		return journal_id or None
		'''
		journal_id = self.pool.get('account.journal').search(cr, uid, [('type', 'in', ['bank'])], limit=1)
		return journal_id and journal_id[0] or None
		'''

	_defaults = {
		'payment_cash_journal': _default_payment_cash_journal,
		'payment_receivable_journal': _default_payment_receivable_journal,
		'payment_giro_journal' : _default_payment_receivable_journal,
		'payment_transfer_journal' : _default_payment_receivable_journal,
	}


	def onchange_debit_or_credit(self, cr, uid, ids, edc_id, credit_or_debit, context=None):
		if edc_id and credit_or_debit:
			account_journal_edc_obj = self.pool.get('account.journal.edc')
			edc = account_journal_edc_obj.browse(cr, uid, edc_id)
			if credit_or_debit == 'credit':
				card_fee = edc.credit_fee
			elif credit_or_debit == 'debit':
				card_fee = edc.debit_fee
			else:
				card_fee = 0
			return {'value': {
				'card_fee': card_fee
			}}
	
	def onchange_card_fee(self, cr, uid, ids, card_fee, amount_total, context=None):
		return {'value': {'card_fee_amount': card_fee * amount_total / 100}}


	def _make_payment(self, cr, uid, partner_id,amount, payment_method, invoice_id, journal_id=None, context=None):
		
		if payment_method not in ['transfer', 'cash', 'receivable', 'giro']: return False
		if amount <= 0: return False
		if not journal_id:
			raise osv.except_osv(_('Payment Error'), _('Please supply journal for payment method %s.') % payment_method)

		voucher_obj = self.pool.get('account.voucher')
		journal_obj = self.pool.get('account.journal')
		account_move_line_obj = self.pool.get('account.move.line')
		invoice_obj = self.pool.get('account.invoice')
		move_obj = self.pool.get('account.move')

		account_move_ids = account_move_line_obj.search(cr, uid, [
			('invoice','=',invoice_id),
			('account_id.type','=','receivable')
			])
		if len(account_move_ids) == 0:
			raise osv.except_osv(_('Payment Error'),_("There is no receivable account in this invoice's journal."))
		account_move = account_move_line_obj.browse(cr, uid, account_move_ids[0])

		invoice = invoice_obj.browse(cr, uid, invoice_id)
		bon_number = invoice.origin
		journal = journal_obj.browse(cr, uid, journal_id, context)

		# Prepare voucher values for payment
		voucher_vals = {
			'partner_id': partner_id.id,
			'payment_method_type': payment_method,
			'comment': 'Write-Off',
			'payment_option': 'without_writeoff',
			'pre_line': True,
			'amount': amount,
			'type': 'receipt',
			'reference': bon_number,
			'journal_id': journal_id,
			'account_id': journal.default_debit_account_id.id or journal.default_credit_account_id.id,
			'line_cr_ids': [(0, False, {
				'date_due': fields.date.today(),
				'reconcile': True if amount >= account_move.debit - account_move.credit else False,
				'date_original': fields.date.today(),
				'move_line_id': account_move.id,
				'amount_unreconciled': account_move.debit - amount, #account_move.credit,
				'amount': amount,
				'amount_original': account_move.debit,
				'account_id': account_move.account_id.id
			})],
		}

		# Create payment
		voucher_id = voucher_obj.create(cr, uid, voucher_vals, context=context)
		voucher_obj.signal_workflow(cr, uid, [voucher_id], 'proforma_voucher', context=context)

		# browse ulang supaya mendapatkan nilai residual terbaru, setelah ada pembayaran
		# di atas
		# kalau sisa invoice sudah 0, langsung tandai Paid
		invoice = invoice_obj.browse(cr, uid, invoice_id)
		residual = invoice.residual
		if invoice.residual <= 0:
			invoice_obj.write(cr, uid, [invoice_id], {'reconciled': True}, context)

		'''
		account_move_line_obj = self.pool.get('account.move.line')
		account_move_id = account_move_line_obj.search(cr, uid, [('invoice', '=', invoice_id.id)])[0]
		account_move = account_move_line_obj.browse(cr, uid, [account_move_id])

		journal_obj = self.pool.get('account.journal')
		if not journal_id:
			journal_obj = self.pool.get('account.journal')
			if payment_method == 'transfer':
				journal_id = journal_obj.search(cr, uid, [('type', 'in', ['bank'])], limit=1)
				pass
			elif payment_method == 'cash':
				journal_id = journal_obj.search(cr, uid, [('type', 'in', ['cash'])], limit=1)
				pass
			elif payment_method == 'receivable':
				journal_id = journal_obj.search(cr, uid, [('type', 'in', ['bank'])], limit=1)
				pass
			elif payment_method == 'giro':
				journal_id = journal_obj.search(cr, uid, [('type', 'in', ['bank'])], limit=1)
				pass
		#user_data = self.pool['res.users'].browse(cr, uid, uid)
		#default_account_sales = user_data.branch_id.default_account_sales
		journal = journal_obj.browse(cr, uid, journal_id, context)
		account_id = journal.default_debit_account_id.id or journal.default_credit_account_id.id

		voucher_vals = {
			'invoice_id': invoice_id.id,
			'payment_expected_currency': invoice_id.currency_id.id,
			'invoice_type': invoice_id.type,
			'partner_id': partner_id,
			'journal_id': journal_id,
			'type': invoice_id.type in ('out_invoice','out_refund') and 'receipt' or 'payment',
			'reference': invoice_id.origin,
			'amount': amount,
			'account_id': account_id,
			'payment_method_type': payment_method,
			'comment': 'Write-Off',
			'payment_option': 'without_writeoff',
			'line_cr_ids': [(0, False, {
				'date_due': fields.date.today(),
				'reconcile': True if amount >= account_move.debit - account_move.credit else False,
				'date_original': fields.date.today(),
				'move_line_id': account_move.id,
				'amount_unreconciled': account_move.debit - account_move.credit,
				'amount': amount,
				'amount_original': account_move.debit,
				'account_id': account_move.account_id.id
			})],
			}	

		voucher_obj = self.pool.get('account.voucher')
		voucher_id = voucher_obj.create(cr, uid,voucher_vals,context)
		voucher_obj.signal_workflow(cr, uid, [voucher_id], 'proforma_voucher', context)

	# if residual==0, paid
		if invoice_id.residual == 0:
			invoice_obj = self.pool.get('account.invoice')
			invoice_obj.write(cr, uid, [invoice_id.id], {'reconciled': True}, context)
			pass
		return True
		'''		

	def action_pay(self, cr, uid, ids, context=None):
		if not ids: return True
		
		additional_payment = self.browse(cr, uid, ids[0])
		so = additional_payment.sale_order_id
		# Asumsi so cuman ada 1 dan sudah ada untuk so yang bersangkutan
		invoice = so.invoice_ids[0]
		
		context.update({
			#'default_type': inv.type in ('out_invoice','out_refund') and 'receipt' or 'payment',
		})
		
		if additional_payment.payment_transfer_amount > 0:
			self._make_payment(cr, uid, invoice.partner_id, additional_payment.payment_transfer_amount, 'transfer', invoice.id, journal_id=additional_payment.payment_transfer_journal.id,context=context),
		if additional_payment.payment_cash_amount > 0:
			self._make_payment(cr, uid, invoice.partner_id, additional_payment.payment_cash_amount, 'cash', invoice.id, journal_id=additional_payment.payment_cash_journal.id,context=context)
		if additional_payment.payment_receivable_amount > 0:
			self._make_payment(cr, uid, invoice.partner_id, additional_payment.payment_receivable_amount, 'receivable', invoice.id, journal_id=additional_payment.payment_receivable_journal.id,context=context)
		if additional_payment.payment_giro_amount > 0:
			self._make_payment(cr, uid, invoice.partner_id, additional_payment.payment_giro_amount, 'giro',invoice.id, journal_id=additional_payment.payment_giro_journal.id,context=context)
		
		'''
		journal_obj = self.pool.get('account.journal')
		journal_id = journal_obj.search(cr, uid, [('type', 'in', ['cash'])], limit=1)
		user_data = self.pool['res.users'].browse(cr, uid, uid)
		default_account_sales = user_data.default_account_sales_override or user_data.branch_id.default_account_sales
		journal = journal_obj.browse(cr, uid, journal_id, context)
		if default_account_sales:
			account_id = default_account_sales.id
		else:
			account_id = journal.default_debit_account_id.id or journal.default_credit_account_id.id
			
		print 'invoice origin=' + str(invoice.origin)
		print 'invoice id=' + str(invoice.id)
		print 'journal=' + str(invoice.journal_id.id)
		print 'amount=' + str(invoice.partner_id.id)
		
		account_move_line_obj = self.pool.get('account.move.line')
		account_move_id = account_move_line_obj.search(cr, uid, [('invoice', '=', invoice.id)])[0]
		account_move = account_move_line_obj.browse(cr, uid, [account_move_id])

		voucher_vals = {
			'invoice_id': invoice.id,
			'payment_expected_currency': invoice.currency_id.id,
			'invoice_type': invoice.type,
			'partner_id': invoice.partner_id.id, #self.pool.get('res.partner')._find_accounting_partner(invoice.partner_id).id,
			'journal_id': journal_id[0],#invoice.journal_id.id,
			'type': invoice.type in ('out_invoice','out_refund') and 'receipt' or 'payment',
			'reference': invoice.origin,
			'amount': additional_payment.payment_cash_amount,
			'account_id': account_id,#invoice.account_id.id,
			#'line_dr_ids': [(0, False, {
			#	'type': 'dr' if invoice.type == 'in_invoice' else 'cr',
			#	'account_id': account_id,
			#	'amount': additional_payment.payment_cash_amount,
			#	})]
			# 'date': canvas_data.date_delivered,
			# 'pay_now': 'pay_now',
			# 'date_due': canvas_data.date_delivered,
			# 'line_dr_ids': [(0, False, {
			# 	'type': 'dr' if inv.type == 'in_invoice' else 'cr',
			# 	'account_id': inv.account_id.id,
			# 	'partner_id': inv.partner_id.id,
			# 	'amount': inv.type in ('out_refund', 'in_refund') and -inv.residual or inv.residual,
			# 	'move_line_id': move_line_id,
			# 	'reconcile': True,	
			'line_cr_ids': [(0, False, {
				'date_due': fields.date.today(),
				'reconcile': True if  additional_payment.payment_cash_amount >= account_move.debit - account_move.credit else False,
				'date_original': fields.date.today(),
				'move_line_id': account_move.id,
				'amount_unreconciled': account_move.debit - account_move.credit,
				'amount': additional_payment.payment_cash_amount,
				'amount_original': account_move.debit,
				'account_id': account_move.account_id.id
			})],		
		}


		if additional_payment.payment_cash_amount:
			voucher_obj = self.pool.get('account.voucher')
			new_voucher_id = voucher_obj.create(cr, uid,voucher_vals,context)
			voucher_obj.proforma_voucher(cr, uid, [new_voucher_id])
		'''
		return True

# ==========================================================================================================================

# class sale_register_add_payment(osv.osv_memory):
# 	_name = "sale.register.add.payment"
# 	_description = 'Sale Register Add Payment'
#
# 	# COLUMNS ---------------------------------------------------------------------------------------------------------------
#
# 	_columns = {
# 		'payment_transfer_amount': fields.float('Transfer Amount'),
# 		'payment_cash_amount': fields.float('Cash Amount'),
# 		'payment_receivable_amount': fields.float('EDC Amount'),
# 		#'unpaid_amount' : inv.type in ('out_refund', 'in_refund') and -inv.residual or inv.residual,
# 	}
#
# 	#FUNCTION ---------------------------------------------------------------------------------------------------------------
#
# 	def button_register_multiple_payment(self, cr, uid, ids, context=None):
# 		return {'type': 'ir.actions.act_window_close'}
