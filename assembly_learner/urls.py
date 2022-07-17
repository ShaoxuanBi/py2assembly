from django.urls import path

from . import apps, views

app_name = apps.AssemblyLearnerConfig.name

urlpatterns = [
    path('page/<str:page>', views.PageView.as_view(), name='page'),
    path('editor/<int:id>', views.EditorView.as_view(), name='editor'),
    path('', views.IndexView.as_view(), name='index'),
    # path('<int:question_id>/', views.detail, name='detail'),
    # path('<int:question_id>/results/', views.results, name='results'),
    # path('<int:question_id>/vote/', views.vote, name='vote'),
]
