#! /usr/bin/env python
# -*- encoding: utf-8 -*-

# Extra Libs
from flask import request, render_template, flash, redirect, url_for, \
    jsonify

# Custom Tools
from ..application import app
from ..tools.erp import openerp
from ..tools.auth import requires_auth
from ..models.models import get_openerp_object
from ..models.obs_sale_order import (
    change_sale_order_note,
    get_current_sale_order,
    get_current_sale_order_id,
    set_quantity,
    add_quantity,
)


# ############################################################################
# Shopping Cart Management Routes
# ############################################################################
@app.route("/shopping_cart")
@requires_auth
def shopping_cart():
    if not get_current_sale_order_id():
        return redirect(url_for('home'))
    return render_template('shopping_cart.html')


@app.route('/shopping_cart_note_update', methods=['POST'])
def shopping_cart_note_update():
    res = change_sale_order_note(request.form['note'])
    if request.is_xhr:
        return jsonify(result=res)
    flash(res['message'], res['state'])
    return redirect(url_for('shopping_cart.html'))


@app.route('/shopping_cart_quantity_update', methods=['POST'])
def shopping_cart_quantity_update():
    line_id = int(request.form['line_id'])
    res = sanitize_qty(request.form['new_quantity'])
    if res['state'] != 'success':
        if request.is_xhr:
            return jsonify(result=res)
        else:
            flash(res['message'], res['state'])
            return redirect(url_for('shopping_cart'))

    res = set_quantity(
        line_id, res['quantity'])
    if request.is_xhr:
        return jsonify(result=res)
    else:
        flash(res['message'], res['state'])
        return redirect(url_for('shopping_cart'))


@app.route("/shopping_cart_delete")
@requires_auth
def shopping_cart_delete():
    delete_current_sale_order()
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
    
    if get_current_sale_order_id():
        _("Your shopping cart has been successfully deleted."), 'success')
    else:
        _("Your shopping cart has been successfully deleted."), 'success')
    return shopping_cart()


# ############################################################################
# Recovery Moment Place Route
# ############################################################################
@app.route("/recovery_moment_place")
@requires_auth
def recovery_moment_place():
    company = get_openerp_object(
        'res.company', int(conf.get('openerp', 'company_id')))
    recovery_moment_groups = openerp.SaleRecoveryMomentGroup.browse(
        [('state', 'in', 'pending_sale')])
    sale_order = load_sale_order()
    if (company.eshop_minimum_price != 0
            and company.eshop_minimum_price > sale_order.amount_total):
        flash(
            _("You have not reached the ceiling : ") +
            compute_currency(company.eshop_minimum_price),
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
            'reminder_state': 'to_send',
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
    company = get_openerp_object(
        'res.company', int(conf.get('openerp', 'company_id')))
    sale_order = load_sale_order()
    delivery_moments = openerp.SaleDeliveryMoment.load_delivery_moment_data(
        sale_order.id, company.eshop_minimum_price,
        company.eshop_vat_included)

    if (company.eshop_minimum_price != 0
            and company.eshop_minimum_price > sale_order.amount_total):
        flash(
            _("You have not reached the ceiling : ") +
            compute_currency(company.eshop_minimum_price),
            'warning')
        return redirect(url_for('shopping_cart'))
    return render_template(
        'delivery_moment.html', delivery_moments=delivery_moments)


@app.route("/select_delivery_moment/<int:delivery_moment_id>")
@requires_auth
def select_delivery_moment(delivery_moment_id):
    sale_order = load_sale_order()
    if sale_order:
        if openerp.SaleOrder.select_delivery_moment_id(
                sale_order.id, delivery_moment_id):
            sale_order = load_sale_order()
            if sale_order:
                flash(_(
                    "Your Sale Order has been partially confirmed.\n"
                    " A residual shopping Cart has been created with remaning"
                    " Products."), 'warning')
                return redirect(url_for('shopping_cart'))
            else:
                flash(_("Your Sale Order is now confirmed."), 'success')
                return redirect(url_for('orders'))
        else:
            flash(_(
                "Something wrong happened."
                " Please select again your delivery moment."), 'danger')
            return redirect(url_for('shopping_cart'))
    else:
        flash(_("Your Shopping Cart has been deleted."), 'danger')
        return redirect(url_for('home'))

