from django.urls import path

from . import views

app_name = "dashboard"


detail_urls = [
    path("project/<slug:project_id>/", views.DetailProjectView.as_view(), name="detail_project"),
    path("topic/<slug:topic_id>/", views.DetailTopicView.as_view(), name="detail_topic"),
    path("dataobject/<slug:dataobject_id>", views.DetailDataObjectView.as_view(), name="detail_dataobject"),
]

new_urls = [
    path("project/new/", views.NewProjectView.as_view(), name="new_project"),
    path("topic/new/<slug:project_id>/", views.NewTopicView.as_view(), name="new_topic"),
    path("dataobject/new/<slug:topic_id>", views.NewDataObject.as_view(), name="new_dataobject"),
]

delete_urls = [
    path("project/delete/<slug:project_id>/", views.DeleteProjectView.as_view(), name="delete_project"),
    path("topic/delete/<slug:topic_id>/", views.DeleteTopicView.as_view(), name="delete_topic"),
    path("dataobject/delete/<slug:dataobject_id>", views.DeleteDataObject.as_view(), name="delete_dataobject")
]

edit_urls = [
    path("dataobject/edit/<slug:dataobject_id>", views.EditDataObjectView.as_view(), name="edit_dataobject"),
]

ajax_urls = [
    path("htmx_ajax/topic/mongo_dataobject/<slug:topic_id>", views.QueryDataObjectsView.as_view(), name="query_dataobjects"),
    path("htmx_ajax/mongo_dataobject/values/<slug:dataobject_id>/", views.QueryDataObjectValues.as_view(), name="query_dataobject_values"),
    path("html_ajax/connection/refresh", views.RefreshConnectionsView.as_view(), name="refresh_connections"),
    path("html_ajax/connection/check/<slug:project_id>", views.CheckConnectionView.as_view(), name="check_connection"),
]

download_urls = [
    path("download/dataobject/<slug:dataobject_id>/", views.DownloadView.as_view(), name="download_csv"),
]

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
] + new_urls + delete_urls + detail_urls + ajax_urls + download_urls + edit_urls
