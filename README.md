odoo-eshop
==========

POC for a Flask Website Shop that communicate with Odoo

Installation
------------

* Install Odoo;
* Install librairies;
    * sudo pip install flask
    * sudo pip install flask-babel
    * sudo pip install erppeek


* Install redis:
    * sudo apt-get install redis-server


TODO
----
    * Product quantity:
        * manage minimum_qty and rounding_qty; (and add them in sale-eshop module);

    * shopping_cart:
        * possibility to change quantity;

    * Validate the sale order:
        * select the sale_moment_recovery;

    * at login:
        * display sale_moment_group information;

    * Add password on res.partner and manage it;

    * Make dynamic currency;

    * Make dynamic the choice of locale (fr) for user;

