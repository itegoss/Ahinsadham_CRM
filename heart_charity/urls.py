from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),

    path('login/', views.signin_view, name='login'),
    path("logout", views.logout_view, name="logout"),
    path("request_password_reset/", views.request_password_reset, name="request_password_reset"),
    path("reset_password/<uname>/", views.reset_password, name="reset_password"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("user-dashboard/", views.user_dashboard, name="user_dashboard"),
    path('welcome/', views.welcome_view, name='welcome'),
    path('send-otp/', views.send_otp, name='send_otp'),
    path('access_control/', views.access_control, name='access_control'),
    path('check_module_access/<int:user_id>', views.check_module_access, name='check_module_access'),
    path('search/', views.search_users, name='search_users'),
    path('add_donor_volunteer/', views.add_donor_volunteer, name='add_donor_volunteer'),
    path('adddonation',views.adddonation,name='adddonation'),
    path('donation-list/', views.donation_list, name='donation-list'),
    path('download-donor-report/', views.download_donor_report, name='download_donor_report'),
    path('edit_user/<int:id>/', views.edit_user, name='edit_user'),
    path('delete_user/<int:user_id>/', views.delete_user, name='delete_user'),
path("donation/receipt/<int:id>/", views.donation_receipt, name="donation_receipt"),
path("donation/receipt/pdf/<int:id>/", views.generate_receipt_pdf, name="download_receipt_pdf"),
    path('add_donationbox_payment/', views.add_donationbox_payment, name='add_donationbox_payment'),
    path('add_donation_box/', views.add_donation_box, name='add_donation_box'),
    path('add-employee/', views.add_employee, name='add-employee'),
    path('all_donations/', views.all_donations, name='all_donations'),  # ✅ Add this
    path('donation-boxes/', views.donationbox_list, name='donationbox_list'),
    path('download_filtered_donations/', views.download_filtered_donations, name='download_filtered_donations'),
    path('donation_list',views.donation_list,name='donation_list'),

    path('search_roles/', views.search_roles, name='search_roles'),
    path('search_donor_volunteer/', views.search_donor_volunteer, name='search_donor_volunteer'),
    path('search_donation/', views.search_donation, name='search_donation'),
    path('manage_user_roles/', views.manage_user_roles, name='manage_user_roles'),
    path('assign_role/', views.assign_role, name='assign_role'),




    path('download_filtered_users/', views.download_filtered_users, name='download_filtered_users'),
    path('download_filtered_user_access/', views.download_filtered_user_access, name='download_filtered_user_access'),
    path('download_filtered_donor_volunteers/', views.download_filtered_donor_volunteers, name='download_filtered_donor_volunteers'),

path('user-access-list/', views.user_access_list, name='user_access_list'),

path('search_id/', views.search_id, name='search_id'),
    path('search-users/', views.search_users, name='search_users'),
    path('search-firstname/', views.searchfirstname, name='searchfirstname'),
    path('search-lastname/', views.searchlastname, name='searchlastname'),
    path('search-email/', views.searchemail, name='searchemail'),
    path('search-isstaff/', views.searchisstaff, name='searchisstaff'),
    path('search-active/', views.searchactive, name='searchactive'),
    path('search-superuser/', views.searchsuperuser, name='searchsuperuser'),
    path('search-lastlogin/', views.search_lastlogin, name='search_lastlogin'),
    path('searchdate/', views.searchdate, name='searchdate'),
    path('show_lookup_data/', views.show_lookup_data, name='show_lookup_data'),

    path('lookup_type_create/', views.lookup_type_create, name='lookup_type_create'),
    path("lookup/create/", views.lookup_create, name="lookup_create"),
    path("search-lookup-type/", views.search_lookup_type, name="search_lookup_type"),
    path("search-lookup-table/", views.search_lookup_table, name="search_lookup_table"),


    path("edit-access/<int:id>/", views.edit_usermoduleaccess, name="edit_access"),
path('donor/edit/<int:donor_id>/', views.edit_donor, name='edit_donor'),
# urls.py
path("donation/edit/<int:id>/", views.edit_donation, name="edit_donation"),
    path('lookup-types/<int:id>/edit/', views.edit_lookup_type, name='edit_lookup_type'),
    path("lookup/<int:id>/edit/", views.edit_lookup, name="edit_lookup"),


path('lookup-type/delete/<int:lookup_type_id>/', views.delete_lookup_type, name='delete_lookup_type'),
path('lookup/delete/<int:lookup_id>/', views.delete_lookup, name='delete_lookup'),
path("delete-user-access/<int:access_id>/", views.delete_user_module_access, name="delete_user_module_access"),
path("delete-donor/<int:donor_id>/", views.delete_donor_volunteer, name="delete_donor_volunteer"),
path("delete-donation/<int:donation_id>/", views.delete_donation, name="delete_donation"),

]
