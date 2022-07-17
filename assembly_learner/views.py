# Create your views here.
from pathlib import Path

import markdown
from django.core.handlers.wsgi import WSGIRequest
from django.http import Http404
from django.views.generic import TemplateView

directory_map = {
    'assign': 'Assign',
    'add': 'Add',
    'minus': 'Minus',
    'multiply': 'Multiply',
    'divide': 'Divide',
    'if': 'If',
    'if-else': 'If-Else',
    'for': 'For Loop',
}


class IndexView(TemplateView):
    template_name = 'assembly_learner/index.html'
    extra_context = {
        'directories': directory_map
    }


class PageView(TemplateView):
    template_name = 'assembly_learner/page.html'
    request: WSGIRequest

    @property
    def markdown_source(self):
        page_name = self.kwargs.get('page', '')
        if page_name not in directory_map:
            raise Http404(f'Page "{page_name}" not found.')
        path = Path(__file__).parent / 'pages' / f'{page_name}.md'
        if not path.is_file():
            raise Http404(f'Markdown source for page "{page_name}" not found.')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content

    @property
    def rendered_html(self):
        return markdown.markdown(
            self.markdown_source,
            extensions=[
                'markdown.extensions.extra',
                'markdown.extensions.codehilite',
                # 'markdown.extensions.tables',
                # 'markdown.extensions.def_list',
                # 'markdown.extensions.attr_list',
                # 'markdown.extensions.abbr',
                # 'markdown.extensions.smarty',
            ]
        )

    def get_context_data(self, **kwargs):
        kwargs.update({
            'markdown': self.markdown_source,
            'rendered_html': self.rendered_html,
        })
        return super().get_context_data(**kwargs)


class EditorView(TemplateView):
    template_name = 'assembly_learner/editor.html'
    request: WSGIRequest
