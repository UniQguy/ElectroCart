from django.contrib import admin
from django.urls import path, include

from accounts import views


urlpatterns = [

    # ========================================================
    # ADMIN
    # ========================================================

    path(
        "admin/",
        admin.site.urls
    ),


    # ========================================================
    # SPLASH SCREEN
    # ========================================================

    path(
        "",
        views.splash,
        name="splash"
    ),


    # ========================================================
    # ACCOUNTS
    # ========================================================

    path(
        "",
        include("accounts.urls")
    ),

]