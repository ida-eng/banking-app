from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api, views

router = DefaultRouter()
router.register("accounts", api.AccountViewSet, basename="api-account")
router.register("transactions", api.TransactionViewSet, basename="api-transaction")

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("accounts/<int:pk>/", views.account_detail, name="account"),
    path("accounts/<int:pk>/statement.csv", views.statement_csv, name="statement"),
    path("transfer/", views.transfer, name="transfer"),
    path("recipients/", views.beneficiaries, name="beneficiaries"),
    path("recipients/<int:pk>/delete/", views.beneficiary_delete, name="beneficiary_delete"),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("demo/", views.demo_login, name="demo"),
    path("api/transfers/", api.TransferView.as_view(), name="api-transfer"),
    path("api/", include(router.urls)),
]
