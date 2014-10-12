#! /usr/bin/env python
# -*- encoding: utf-8 -*-

# Standard Librairies
import logging
import io
from datetime import timedelta

# Extra Librairies
from flask import Flask, request, redirect, session, url_for, \
    render_template, flash, abort, send_file
from flask.ext.babel import gettext as _
from flask.ext.babel import Babel

# Custom Modules
from config import conf
from auth import login, logout, requires_auth
from sale_order import add_product, load_sale_order
from erp import openerp, get_invoice_pdf

# Initialization of the Apps
app = Flask(__name__)
app.secret_key = conf.get('flask', 'secret_key')
app.debug = conf.get('flask', 'debug') == 'True'
app.config['BABEL_DEFAULT_LOCALE'] = conf.get('localization', 'locale')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
    minutes=int(conf.get('auth', 'session_minute')))
babel = Babel(app)


@babel.localeselector
def locale_selector():
    if 'partner_id' in session:
        partner = openerp.ResPartner.browse(session['partner_id'])
        return partner.lang
    return request.accept_languages.best_match(['fr', 'en'])


def partner_domain():
    if 'partner_id' in session:
        return ('partner_id', '=', session['partner_id'])
    else:
        return ('partner_id', '=', -1)


@app.template_filter('currency')
def currency(n):
    return ('%.02f' % n).replace('.', ',') + u' €'


# Auth Route
@app.route("/login.html", methods=['POST'])
def login_view():
    login(request.form['login'], request.form['password'])
    return redirect(request.args['return_to'])


@app.route("/logout.html")
def logout_view():
    logout()
    return redirect(url_for('home'))


@app.route("/")
@requires_auth
def home():
    return render_template(
        'home.html'
    )


@app.route("/invoices")
@requires_auth
def invoices():
    account_invoices = openerp.AccountInvoice.browse(
        [partner_domain()])
    return render_template(
        'invoices.html', account_invoices=account_invoices
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


@app.route("/shopping_cart")
@requires_auth
def shopping_cart():
    sale_order = load_sale_order()
    return render_template(
        'shopping_cart.html',
        sale_order=sale_order,
    )


@app.route('/shopping_cart/quantity_update', methods=['POST'])
def quantity_update():
    print request.form
    if request.is_xhr:
        return '{"line_total": "100"}', 200
    return redirect(url_for('shopping_cart'))


@app.route("/recovery_moment_place")
@requires_auth
def recovery_moment_place():
    recovery_moment_groups = openerp.SaleRecoveryMomentGroup.browse(
        [('state', 'in', 'pending_sale')])
    return render_template(
        'recovery_moment_place.html',
        recovery_moment_groups=recovery_moment_groups,
    )


@app.route("/delete_shopping_cart")
@requires_auth
def delete_shopping_cart():
    sale_order = load_sale_order()
    sale_order.unlink()
    return render_template(
        'home.html',
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
        # TODO Add flash
        return redirect(url_for('home'))
    else:
        # TODO do something
        pass


@app.route("/delete_sale_order_line/<int:sale_order_line_id>")
@requires_auth
def delete_sale_order_line(sale_order_line_id):
    sale_order = load_sale_order()
    if len(sale_order.order_line) > 1:
        for order_line in sale_order.order_line:
            if order_line.id == sale_order_line_id:
                order_line.unlink()
        return shopping_cart()
    else:
        return delete_shopping_cart()


@app.route("/product/<int:product_id>", methods=['GET', 'POST'])
@requires_auth
def product(product_id):
    # Get Products
    product = openerp.ProductProduct.browse(product_id)

    # Add product to shopping cart if wanted
    if request.method == 'POST':
        try:
            quantity = float(
                request.form['quantity'].replace(',', '.').strip())
        except ValueError:
            quantity = False
            flash(_('Invalid Quantity'), 'error')
        if quantity:
            add_product(product, quantity)

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


@app.route('/catalog/', defaults={'category_id': False})
@app.route("/catalog/<int:category_id>")
@requires_auth
def catalog(category_id):
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
        'catalog.html',
        categories=categories,
        parent_categories=parent_categories,
        current_category=current_category,
        products=products,
    )


@app.context_processor
def current_sale_order():
    return {'sale_order': load_sale_order()}


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(Exception)
def error(e):
    logging.exception('an error occured')
    return render_template('error.html'), 500
