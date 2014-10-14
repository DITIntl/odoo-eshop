#! /usr/bin/env python
# -*- encoding: utf-8 -*-

# Standard Librairies
import logging
import io
from datetime import timedelta

# Extra Librairies
from flask import Flask, request, redirect, session, url_for, \
    render_template, flash, abort, send_file, jsonify
from flask.ext.babel import gettext as _
from flask.ext.babel import Babel

# Custom Modules
from config import conf
from auth import login, logout, requires_auth
from sale_order import load_sale_order, delete_sale_order, \
    currency, change_product_qty

from erp import openerp, get_invoice_pdf, get_order_pdf, get_account_qty

# Initialization of the Apps
app = Flask(__name__)
app.secret_key = conf.get('flask', 'secret_key')
app.debug = conf.get('flask', 'debug') == 'True'
app.config['BABEL_DEFAULT_LOCALE'] = conf.get('localization', 'locale')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
    minutes=int(conf.get('auth', 'session_minute')))
babel = Babel(app)


@app.context_processor
def current_sale_order():
    sale_order = load_sale_order()
    return {'sale_order': sale_order}


@babel.localeselector
def locale_selector():
    if 'partner_id' in session:
        partner = openerp.ResPartner.browse(session['partner_id'])
        return partner.lang
    return request.accept_languages.best_match(['fr', 'en'])


def partner_domain(partner_field):
    if 'partner_id' in session:
        return (partner_field, '=', session['partner_id'])
    else:
        return (partner_field, '=', -1)


@app.template_filter('currency')
def compute_currency(amount):
    return currency(amount)


@app.template_filter('get_current_quantity')
def get_current_quantity(product_id):
    sale_order = load_sale_order()
    if sale_order:
        for line in sale_order.order_line:
            if line.product_id.id == product_id:
                return line.product_uom_qty
    return 0


# TODO FIXME: Problem with erpeek. Text of field selection unavaible
@app.template_filter('fresh_category')
def fresh_category(value):
    return {
        'extra': _('Extra'),
        '1': _('Category I'),
        '2': _('Category II'),
        '3': _('Category III'),
    }[value]


@app.template_filter('not_null')
def not_null(value):
    return value if value else _('Undefined')


# ############################################################################
# Home Route
# ############################################################################
@app.route("/")
@requires_auth
def home():
    return render_template(
        'home.html'
    )


# ############################################################################
# Auth Route
# ############################################################################
@app.route("/login.html", methods=['POST'])
def login_view():
    login(request.form['login'], request.form['password'])
    return redirect(request.args['return_to'])


@app.route("/logout.html")
def logout_view():
    logout()
    return redirect(url_for('home'))


# ############################################################################
# Product Routes
# ############################################################################
@app.route("/product/<int:product_id>")
@requires_auth
def product(product_id):
    # Get Products
    product = openerp.ProductProduct.browse(product_id)

    # Get Parent Categories
    parent_categories = []
    parent = product.eshop_category_id
    while parent:
        parent_categories.insert(0, {'id': parent.id, 'name': parent.name})
        parent = parent.parent_id

    return render_template(
        'product.html', product=product,
        parent_categories=parent_categories,
    )


@app.route("/product_add_qty/<int:product_id>", methods=['POST'])
@requires_auth
def product_add_qty(product_id):
    res = change_product_qty(
        request.form['quantity'], 'add', product_id=product_id)
    flash(res['message'], res['state'])
    return redirect(url_for('product', product_id=product_id))


# ############################################################################
# Catalog (Tree View) Routes
# ############################################################################
@app.route('/catalog_tree/', defaults={'category_id': False})
@app.route("/catalog_tree/<int:category_id>")
@requires_auth
def catalog_tree(category_id):
    parent_categories = []
    current_category = False

    # Get Child Categories
    categories = openerp.eshopCategory.browse(
        [('parent_id', '=', category_id)])

    parent_categories = []
    # Get Parent Categories
    if category_id:
        current_category = openerp.eshopCategory.browse(category_id)
        # Get Parent Categories
        parent = current_category
        while parent:
            parent_categories.insert(
                0, {'id': parent.id, 'name': parent.name})
            parent = parent.parent_id

    # Get Products
    products = openerp.ProductProduct.browse(
        [('eshop_ok', '=', True), ('eshop_category_id', '=', category_id)],
        order='name')
    return render_template(
        'catalog_tree.html',
        categories=categories,
        parent_categories=parent_categories,
        current_category=current_category,
        products=products,
    )


# ############################################################################
# Catalog (Inline View) Routes
# ############################################################################
@app.route('/catalog_inline/', defaults={'category_id': False})
@app.route("/catalog_inline/<int:category_id>")
@requires_auth
def catalog_inline(category_id):
    # Get Child Categories
    categories = openerp.eshopCategory.browse(
        [('type', '=', 'normal')])
    return render_template(
        'catalog_inline.html',
        categories=categories,
    )


@app.route('/catalog_inline_quantity_update', methods=['POST'])
def catalog_inline_quantity_update():
    res = change_product_qty(
        request.form['new_quantity'], 'set',
        product_id=int(request.form['product_id']))
    if request.is_xhr:
        return jsonify(result=res)
    flash(res['message'], res['state'])
    return redirect(url_for('catalog_inline'))


# ############################################################################
# Shopping Cart Management Routes
# ############################################################################
@app.route("/shopping_cart")
@requires_auth
def shopping_cart():
    sale_order = load_sale_order()
    return render_template(
        'shopping_cart.html',
        sale_order=sale_order,
    )


@app.route('/shopping_cart_quantity_update', methods=['POST'])
def shopping_cart_quantity_update():
    try:
        tmp = float(request.form['new_quantity'])
    except:
        tmp = 1
    if tmp == 0:
        res = {'state': 'danger', 'message': 'Null Quantity'}
        if request.is_xhr:
            return jsonify(result=res)
        else:
            flash(res['message'], res['state'])
            return redirect(url_for('shopping_cart'))

    res = change_product_qty(
        request.form['new_quantity'], 'set',
        line_id=int(request.form['line_id']))
    if request.is_xhr:
        return jsonify(result=res)
    flash(res['message'], res['state'])
    return redirect(url_for('shopping_cart'))


@app.route("/shopping_cart_delete")
@requires_auth
def shopping_cart_delete():
    delete_sale_order()
    flash(_("Your shopping cart has been successfully deleted."), 'success')
    return render_template('home.html')


@app.route("/shopping_cart_delete_line/<int:line_id>")
@requires_auth
def shopping_cart_delete_line(line_id):
    sale_order = load_sale_order()
    if len(sale_order.order_line) > 1:
        for order_line in sale_order.order_line:
            if order_line.id == line_id:
                order_line.unlink()
        return shopping_cart()
    else:
        return shopping_cart_delete()


# ############################################################################
# Recovery Moment Place Route
# ############################################################################
@app.route("/recovery_moment_place")
@requires_auth
def recovery_moment_place():
    recovery_moment_groups = openerp.SaleRecoveryMomentGroup.browse(
        [('state', 'in', 'pending_sale')])
    return render_template(
        'recovery_moment_place.html',
        recovery_moment_groups=recovery_moment_groups,
    )


@app.route("/select_recovery_moment/<int:recovery_moment_id>")
@requires_auth
def select_recovery_moment(recovery_moment_id):
    found = False
    recovery_moment_groups = openerp.SaleRecoveryMomentGroup.browse(
        [('state', 'in', 'pending_sale')])
    sale_order = load_sale_order()
    for recovery_moment_group in recovery_moment_groups:
        for recovery_moment in recovery_moment_group.moment_ids:
            if recovery_moment.id == recovery_moment_id:
                found = True
                break
    if found:
        openerp.SaleOrder.write(sale_order.id, {
            'moment_id': recovery_moment_id,
            })
        openerp.SaleOrder.action_button_confirm([sale_order.id])
        flash(_("Your Sale Order is now confirmed."), 'success')
        return redirect(url_for('home'))
    else:
        # TODO do something
        pass


# ############################################################################
# Account Route
# ############################################################################
@app.route("/account")
@requires_auth
def account():
    partner = openerp.ResPartner.browse(session['partner_id'])
    orders_qty, invoices_qty = get_account_qty(session['partner_id'])
    return render_template(
        'account.html', partner=partner,
        orders_qty=orders_qty, invoices_qty=invoices_qty,
    )


# ############################################################################
# Orders Route
# ############################################################################
@app.route("/orders")
@requires_auth
def orders():
    orders = openerp.SaleOrder.browse([
        partner_domain('partner_id'),
        ('state', 'not in', ('draft', 'cancel'))])
    orders_qty, invoices_qty = get_account_qty(session['partner_id'])
    return render_template(
        'orders.html', orders=orders,
        orders_qty=orders_qty, invoices_qty=invoices_qty,
    )


@app.route('/order/<int:order_id>/download')
def order_download(order_id):
    order = openerp.SaleOrder.browse(order_id)
    if not order or order.partner_id.id != session['partner_id']:
        return abort(404)

    content = get_order_pdf(order_id)
    filename = "%s_%s.pdf" % (_('order'), order.name.replace('/', '_'))
    return send_file(
        io.BytesIO(content),
        as_attachment=True,
        attachment_filename=filename,
        mimetype='application/pdf'
    )


# ############################################################################
# Invoices Route
# ############################################################################
@app.route("/invoices")
@requires_auth
def invoices():
    invoices = openerp.AccountInvoice.browse([
        partner_domain('partner_id'),
        ('state', 'not in', ('draft', 'proforma', 'proforma2', 'cancel'))])
    orders_qty, invoices_qty = get_account_qty(session['partner_id'])
    return render_template(
        'invoices.html', invoices=invoices,
        orders_qty=orders_qty, invoices_qty=invoices_qty,
    )


@app.route('/invoices/<int:invoice_id>/download')
def invoice_download(invoice_id):
    invoice = openerp.AccountInvoice.browse(invoice_id)
    if not invoice or invoice.partner_id.id != session['partner_id']:
        return abort(404)

    content = get_invoice_pdf(invoice_id)
    filename = "%s_%s.pdf" % (_('invoice'), invoice.number.replace('/', '_'))
    return send_file(
        io.BytesIO(content),
        as_attachment=True,
        attachment_filename=filename,
        mimetype='application/pdf'
    )


# ############################################################################
# Technical Routes
# ############################################################################
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(Exception)
def error(e):
    logging.exception('an error occured')
    return render_template('error.html'), 500
