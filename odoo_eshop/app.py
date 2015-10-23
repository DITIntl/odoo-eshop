#! /usr/bin/env python
# -*- encoding: utf-8 -*-

# Standard Librairies
import logging
import io, re
import base64
from datetime import datetime, timedelta
import pytz
from captcha.image import ImageCaptcha

from random import randint

# Extra Librairies
from flask import Flask, request, redirect, session, url_for, \
    render_template, flash, abort, send_file, jsonify
from flask.ext.babel import gettext as _
from flask.ext.babel import Babel

# Custom Modules
from config import conf
from auth import login, logout, requires_auth, requires_connection
from sale_order import load_sale_order, delete_sale_order, \
    currency, change_product_qty, change_shopping_cart_note
from res_partner import change_res_partner

from erp import openerp, tz, get_invoice_pdf, get_order_pdf

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
    try:
        sale_order = load_sale_order()
        return {'sale_order': sale_order}
    except:
        pass
    return {'sale_order': False}


@babel.localeselector
def locale_selector():
    if session.get('partner_id', False):
        try:
            partner = openerp.ResPartner.browse(session['partner_id'])
            return partner.lang
        except:
            pass
    return request.accept_languages.best_match(['fr', 'en'])


def partner_domain(partner_field):
    if 'partner_id' in session:
        return (partner_field, '=', session['partner_id'])
    else:
        return (partner_field, '=', -1)


def get_local_date(str_utc_date, schema):
    """From UTC string Datetime, return local datetime"""
    mytz = pytz.timezone(tz)
    utc_date = datetime.strptime(str_utc_date, schema)
    return mytz.fromutc(utc_date)


@app.template_filter('to_currency')
def compute_currency(amount):
    return currency(amount)


@app.template_filter('function_to_eval')
def function_to_eval(arg):
    return arg


@app.template_filter('to_day')
def to_day(arg):
    if ' ' in arg:
        int_day = get_local_date(arg, '%Y-%m-%d %H:%M:%S').strftime('%w')
    else:
        int_day = get_local_date(arg, '%Y-%m-%d').strftime('%w')
    return {
        '0': _('Sunday'),
        '1': _('Monday'),
        '2': _('Tuesday'),
        '3': _('Wednesdsay'),
        '4': _('Thursday'),
        '5': _('Friday'),
        '6': _('Saturday'),
    }[int_day]


@app.template_filter('to_date')
def to_date(arg):
    if ' ' in arg:
        return get_local_date(arg, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
    else:
        return get_local_date(arg, '%Y-%m-%d').strftime('%d/%m/%Y')


@app.template_filter('to_datetime')
def to_datetime(arg):
    return get_local_date(arg, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %Hh%M')


@app.template_filter('to_time')
def to_time(arg):
    return get_local_date(arg, '%Y-%m-%d %H:%M:%S').strftime('%Hh%M')


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


@app.template_filter('empty_if_null')
def empty_if_null(value):
    return value if value else ''


# ############################################################################
# Home Route
# ############################################################################
@app.route("/")
@requires_connection
def home():
    shop = openerp.SaleShop.browse(int(conf.get('openerp', 'shop_id')))
    return render_template('home.html', shop=shop)


@app.route("/home_logged.html")
@requires_auth
def home_logged():
    shop = openerp.SaleShop.browse(int(conf.get('openerp', 'shop_id')))
    # TODO Message if PZI
    return render_template('home.html', shop=shop)


@app.route("/unavailable_service.html")
@requires_auth
def unavailable_service():
    return render_template('unavailable_service.html')

# ############################################################################
# Auth Route
# ############################################################################
@app.route("/login.html", methods=['GET', 'POST'])
@requires_connection
def login_view():
    if request.form.get('login', False):
        # Authentication asked
        partner_id = openerp.ResPartner.login(
            request.form['login'], request.form['password'])
        if partner_id:
            partner = openerp.ResPartner.browse(partner_id)
            session['partner_id'] = partner.id
            session['partner_name'] = partner.name
            return redirect(url_for('home_logged'))
        else:
            flash(_('Login/password incorrects'), 'danger')
    return render_template('login.html')


@app.route("/logout.html")
@requires_connection
def logout_view():
    logout()
    return redirect(url_for('home'))

def sanitize_email(txt_email):
    # TODO
    return txt_email

def password_check(password):
    """
    From : http://stackoverflow.com/questions/16709638/
        checking-the-strength-of-a-password-how-to-check-conditions
    Copyright : http://stackoverflow.com/users/3856785/epi27231423
    Verify the strength of 'password'
    Returns a dict indicating the wrong criteria
    A password is considered strong if:
        8 characters length or more
        1 digit or more
        1 symbol or more
        1 uppercase letter or more
        1 lowercase letter or more
    """

    # calculating the length
    length_error = len(password) < 8

    # searching for digits
    digit_error = re.search(r"\d", password) is None

    # searching for uppercase
    uppercase_error = re.search(r"[A-Z]", password) is None

    # searching for lowercase
    lowercase_error = re.search(r"[a-z]", password) is None

    # overall result
    password_ok = not (
        length_error or digit_error or uppercase_error or lowercase_error)

    return {
        'password_ok' : password_ok,
        'length_error' : length_error,
        'digit_error' : digit_error,
        'uppercase_error' : uppercase_error,
        'lowercase_error' : lowercase_error,
    }

@app.route("/register.html", methods=['GET', 'POST'])
@requires_connection
def register():
    # Check if the operation is possible
    if not session.get('eshop_register_allowed', False)\
            or session.get('partner_login', False):
        return redirect(url_for('home'))
    previous_captcha = session.get('captcha', False)
    PATH_TTF = ['/tmp/test.ttf']
    image = ImageCaptcha(fonts=PATH_TTF)

    new_captcha = str(randint(0,999999)).replace('1', '3').replace('7', '4')
    captcha_data = base64.b64encode(image.generate(new_captcha).getvalue())
    session['captcha'] = new_captcha

    if len(request.form) == 0:
        session['captcha_ok'] = False
    else:
        # TODO refactor in a extra file or in Odoo
        complete_data = mail_ok = password_ok = True
        # Check captcha
        if not session.get('captcha_ok', False) and\
                request.form.get('captcha', False) != previous_captcha:
            flash(
                _("The 'captcha' field is not correct. Please try again"),
                'danger')
            return render_template(
                'register.html', captcha_data=captcha_data)
        else:
            session['captcha_ok'] = True

        email = sanitize_email(request.form.get('email', False))
        if email:
            # Check email in Database (inactive account)
            partner_ids = openerp.ResPartner.search([
                ('email', '=', email)])
            if len(partner_ids) > 1:
                mail_ok = False
                flash(_(
                    "The '%(email)s' field is already used."
                    "Please ask your seller to fix the problem.",
                    email=email) , 'danger')
            elif len(partner_ids) == 1:
                mail_ok = False
                partner = openerp.ResPartner.browse(partner_ids)[0]
                if partner.eshop_active:
                    flash(_(
                        "The '%(email)s' field is already associated to an"
                        " active account. Please ask your seller if you"
                        " forgot your credentials.",
                        email=email) , 'danger')
                elif partner.eshop_state == 'email_to_confirm':
                    flash(_(
                        "The '%(email)s' field is already associated to an"
                        " account. Please finish the process to create an"
                        " account, by clicking on the link you received "
                        " by email.", email=email), 'danger')
                else:
                    flash(_(
                        "The '%(email)s' field is already associated to an"
                        " inactive account. Please ask your seller to fix"
                        " the problem.", email=email), 'danger')

        if not mail_ok:
            return render_template('register.html')

        # Check Password
        if request.form.get('password_1') != request.form.get('password_2'):
            # Check consistencies
            password_ok = False
            flash(_("The 'Password' Fields do not match."), 'danger')
        else:
            # Check quality
            res = password_check(request.form.get('password_1'))
            if not res['password_ok']:
                password_ok = False
            for item in [
                {'name': 'length_error', 'description': _(
                    'Password must have 8 characters or more.')},
                {'name': 'digit_error', 'description': _(
                    'Password must have at least one digit.')},
                {'name': 'uppercase_error', 'description': _(
                    'Password must have at least one uppercase characters.')},
                {'name': 'lowercase_error', 'description': _(
                    'Password must have at least one lowercase characters.')}]:
                if res[item['name']]:
                    flash(item['description'], 'danger')

        if complete_data and mail_ok and password_ok:
            # Registration is over
            openerp.ResPartner.create_from_eshop({
                'first_name': request.form['first_name'],
                'last_name': request.form['last_name'],
                'email': request.form['email'],
                'street': request.form['street'],
                'street2': request.form['street2'],
                'zip': request.form['zip'],
                'city': request.form['city'],
                'eshop_password': request.form['password_1'],
            })
            flash(_(
                "The registration is complete. Please check your mail box"
                " '%(email)s' and click on the link you received to activate"
                " your account.",
                email=request.form['email']), 'success')
            return redirect(url_for('home'))
        else:
            return render_template('register.html')

    return render_template('register.html', captcha_data=captcha_data)

@app.route("/activate_account/<int:id>/<string:email>", methods=['GET'])
#@requires_no_auth
def activate_account(id, email):
    partner = openerp.ResPartner.browse([id])[0]
    if not partner or partner.email != email:
        flash(_("The validation process failed."), 'danger')
    elif partner.eshop_state in ['first_purchase', 'enabled']:
        flash(_("Your account is already enabled."), 'warning')
    elif partner.eshop_state in ['email_to_confirm']:
        openerp.ResPartner.write([partner.id], {
            'email_state': 'first_purchase'})
        flash(_("The validation process is over.\n"
        " You can now log in to begin to purchase."), 'success')
    else:
        flash(_(
            "The validation process failed because your account is disabled."
            " Please ask your seller to fix the problem."), 'warning')
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
    products = openerp.ProductProduct.browse([
        ('eshop_state', '=', 'available'),
        ('eshop_category_id', '=', category_id)], order='name')
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
    sale_order = load_sale_order()
    catalog_inline = openerp.saleOrder.get_current_eshop_product_list(
        sale_order and sale_order.id or False)
    return render_template(
        'catalog_inline.html', catalog_inline=catalog_inline)


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

@app.route('/shopping_cart_note_update', methods=['POST'])
def shopping_cart_note_update():
    res = change_shopping_cart_note(
        request.form['note'],
    )
    if request.is_xhr:
        return jsonify(result=res)
    flash(res['message'], res['state'])
    return redirect(url_for('account'))

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
    return redirect(url_for('home_logged'))


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
    sale_order = load_sale_order()
    if (session['eshop_minimum_price'] != 0
            and session['eshop_minimum_price'] > sale_order.amount_total):
        flash(
            _("You have not reached the ceiling : ") +
            compute_currency(session['eshop_minimum_price']),
            'warning')
        return redirect(url_for('shopping_cart'))
    return render_template(
        'recovery_moment_place.html',
        recovery_moment_groups=recovery_moment_groups)


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
        openerp.SaleOrder.write([sale_order.id], {
            'recovery_moment_id': recovery_moment_id,
            'recovery_reminder_state': 'to_send',
        })
        openerp.SaleOrder.action_button_confirm([sale_order.id])
        openerp.SaleOrder.send_mail([sale_order.id])
        flash(_("Your Sale Order is now confirmed."), 'success')
        return redirect(url_for('orders'))
    else:
        flash(_(
            "You have selected an obsolete recovery moment."
            " Please try again."), 'error')
        return redirect(url_for('shopping_cart'))


# ############################################################################
# Delivery Moment Place Route
# ############################################################################
@app.route("/delivery_moment")
@requires_auth
def delivery_moment():
    sale_order = load_sale_order()
    delivery_moments = openerp.SaleDeliveryMoment.load_delivery_moment(
        sale_order.id)
    recovery_moment_groups = openerp.SaleRecoveryMomentGroup.browse(
        [('state', 'in', 'pending_sale')])

    if (session['eshop_minimum_price'] != 0
            and session['eshop_minimum_price'] > sale_order.amount_total):
        flash(
            _("You have not reached the ceiling : ") +
            compute_currency(session['eshop_minimum_price']),
            'warning')
        return redirect(url_for('shopping_cart'))
    return render_template(
        'delivery_moment.html',
        delivery_moments=delivery_moments,
        recovery_moment_groups=recovery_moment_groups)

@app.route("/select_delivery_moment/<int:delivery_moment_id>")
@requires_auth
def select_delivery_moment(delivery_moment_id):
    openerp.SaleOrder.select_delivery_moment_id(
        [sale_order.id], delivery_moment_id)

    flash(_("Your Sale Order is now confirmed."), 'success')
    return redirect(url_for('orders'))
#    return redirect(url_for('shopping_cart'))


# ############################################################################
# Account Route
# ############################################################################
@app.route("/account")
@requires_auth
def account():
    partner = openerp.ResPartner.browse(session['partner_id'])
    return render_template('account.html', partner=partner)


@app.route('/account_update', methods=['POST'])
def account_update():
    res = change_res_partner(
        session['partner_id'],
        request.form['new_phone'],
        request.form['new_mobile'],
        request.form['new_street'],
        request.form['new_street2'],
        request.form['new_zip'],
        request.form['new_city'],
    )
    if request.is_xhr:
        return jsonify(result=res)
    flash(res['message'], res['state'])
    return redirect(url_for('account'))

# ############################################################################
# Orders Route
# ############################################################################
@app.route("/orders")
@requires_auth
def orders():
    orders = openerp.SaleOrder.browse([
        partner_domain('partner_id'),
        ('state', 'not in', ('draft', 'cancel'))])
    return render_template('orders.html', orders=orders)


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
    return render_template('invoices.html', invoices=invoices)


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
    flash(_(
        "An unexcepted error occured. Please try again in a while"), 'danger')
    logging.exception('an error occured')
    return render_template('error.html'), 500
