/******************************************************************************
    eShop for Odoo
    Copyright (C) 2015-Today GRAP (http://www.grap.coop)
    @author Sylvain LE GAL (https://twitter.com/legalsylvain)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as
    published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
******************************************************************************/


$('.input-quantity').change(function(e){
    self = this;
    var new_quantity = e.currentTarget.value;
    var product_id = e.currentTarget.id.split('_')[1];
    $.ajax({
        url: FLASK_URL_FOR['shopping_cart_quantity_update'],
        type: "POST",
        data: {new_quantity: new_quantity, product_id: product_id},
        timeout: 1000,
    }).done(function(msg){
        if (msg.result.state == 'success' || msg.result.state == 'warning'){
            // Update Sale Order Line infos
            $('#quantity_' + product_id).val(msg.result.quantity);
            $('#quantity_' + product_id).toggleClass('input-surcharge', (msg.result.discount < '0'));
            $('#price_subtotal_' + product_id).attr('placeholder', msg.result.amount_line);
            // Update Sale Order infos
            $('#amount_untaxed').attr('placeholder', msg.result.amount_untaxed);
            $('#amount_tax').attr('placeholder', msg.result.amount_tax);
            $('#amount_total').attr('placeholder', msg.result.amount_total);
        }
        update_header(msg.result.order_id, msg.result.amount_total_header, msg.result.minimum_ok);
        display_message(msg.result.state, msg.result.message, false);
    }).fail(function(xhr, textstatus){
        display_fail_message();
    });
});
