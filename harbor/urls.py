from django.contrib.auth.views import LogoutView
from django.urls import path
from commerce import views, metrics
urlpatterns = [
    path("login/",views.WorkspaceLoginView.as_view(),name="login"),
    path("logout/",LogoutView.as_view(),name="logout"),
    path("",views.dashboard,name="dashboard"),
    path("catalog/",views.catalog,name="catalog"),
    path("orders/",views.orders_page,name="orders"),
    path("orders/<uuid:order_id>/",views.order_detail,name="order"),
    path("approvals/",views.orders_page,{"queue":"approvals"},name="approvals"),
    path("fulfillment/",views.orders_page,{"queue":"fulfillment"},name="fulfillment"),
    path("inventory/",views.inventory,name="inventory"),
    path("finance/",views.finance,name="finance"),
    path("returns/",views.returns_page,name="returns"),
    path("operations/",views.operations,name="operations"),
    path("audit/",views.audit_page,name="audit"),
    path("notifications/",views.notifications,name="notifications"),
    path("api/cart/",views.cart_api,name="api-cart"),
    path("api/checkout/",views.checkout_api,name="api-checkout"),
    path("api/orders/<uuid:order_id>/",views.order_api,name="api-order"),
    path("api/orders/<uuid:order_id>/action/",views.order_action_api,name="api-order-action"),
    path("api/stock/<int:stock_id>/",views.stock_api,name="api-stock"),
    path("api/invoices/<int:invoice_id>/payment/",views.payment_api,name="api-payment"),
    path("api/returns/<int:case_id>/",views.return_api,name="api-return"),
    path("api/outbox/<uuid:event_id>/replay/",views.replay_api,name="api-replay"),
    path("api/notifications/<int:notification_id>/read/",views.notification_api,name="api-notification"),
    path("healthz",views.health,name="health"),
    path("readyz",views.readiness,name="readiness"),
    path("metrics",metrics.metrics,name="metrics"),
]
handler403 = views.error403
handler404 = views.error404
