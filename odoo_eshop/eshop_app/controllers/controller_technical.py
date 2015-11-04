#! /usr/bin/env python
# -*- encoding: utf-8 -*-

# Standard Lib
import logging
from datetime import datetime
import pytz

# Extra Lib
from flask import request, session, render_template, flash

from flask.ext.babel import gettext as _

# Custom Tools
from ..application import app
from ..application import babel

from ..tools.config import conf
from ..tools.auth import requires_connection
from ..tools.erp import openerp, tz

# Custom Models
from eshop_app.models.models import get_openerp_object, \
    invalidate_openerp_object

from ..models.obs_sale_order import load_sale_order, currency


# ############################################################################
# Context Processor
# ############################################################################
@app.context_processor
def utility_processor():
    def get_object(model_name, id):
        return get_openerp_object(model_name, id)

    def get_company():
        return get_openerp_object(
            'res.company', int(conf.get('openerp', 'company_id')))

    def get_current_sale_order():
        return load_sale_order()

    return dict(
        get_company=get_company, get_object=get_object,
        get_current_sale_order=get_current_sale_order)


# ############################################################################
# Babel Local Selector
# ############################################################################
@babel.localeselector
def locale_selector():
    if session.get('partner_id', False):
        try:
            partner = openerp.ResPartner.browse(session['partner_id'])
            return partner.lang
        except:
            pass
    return request.accept_languages.best_match(['fr', 'en'])


def get_local_date(str_utc_date, schema):
    """From UTC string Datetime, return local datetime"""
    mytz = pytz.timezone(tz)
    utc_date = datetime.strptime(str_utc_date, schema)
    return mytz.fromutc(utc_date)


# ############################################################################
# Template filters
# ############################################################################
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


@app.template_filter('to_ids')
def to_ids(arg):
    return [x.id for x in arg]


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
# Technical Routes
# ############################################################################
@app.route(
    "/invalidation_cache/" +
    "<string:key>/<string:model>/<int:id>/<string:fields_text>/")
@requires_connection
def invalidation_cache(key, model, id, fields_text):
    print "invalidation"
    if key == conf.get('cache', 'invalidation_key'):
        if ',' in fields_text:
            fields = str(fields_text).split(',')
        else:
            fields = [str(fields_text)]
        data_fields = [x for x in fields if 'image' not in x]
        image_fields = [x for x in fields if 'image' in x]
        if len(data_fields):
            print "data_fields : %s" % data_fields
            # Invalidate Object cache
            invalidate_openerp_object(str(model), int(id))
        if len(image_fields):
            print "image_fields : %s" % image_fields
            # Invalidate Root Cache
            # TODO
    return render_template('200.html'), 200


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(Exception)
def error(e):
    flash(_(
        "An unexcepted error occured. Please try again in a while"), 'danger')
    logging.exception('an error occured')
    return render_template('error.html'), 500
