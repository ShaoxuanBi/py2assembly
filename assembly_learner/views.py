# Create your views here.
import traceback
from pathlib import Path

import markdown
from django.core.handlers.wsgi import WSGIRequest
from django.http import Http404
from django.views.generic import TemplateView

from py2assembly import convert

directory_map = {
    'assign': 'Assign',
    'add': 'Add',
    'minus': 'Minus',
    'multiply': 'Multiply',
    'divide': 'Divide',
    'if': 'If',
    'if-else': 'If-Else',
    'while': 'While Loop',
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
    def page_name(self):
        return self.kwargs.get('page', '')

    @property
    def python_code(self):
        if self.request.method == 'POST':
            return self.request.POST.get('code', '')
        python_path = Path(__file__).parent / 'pages' / f'{self.page_name}.py'
        if not python_path.is_file():
            raise Http404(f'Python source for page "{self.page_name}" not found.')
        with open(python_path, 'r', encoding='utf-8') as f:
            python_content = f.read()
        return python_content

    @property
    def assembly_code(self):
        try:
            return convert(self.python_code)
        except:
            traceback.print_exc()
            return 'CONVERT FAILED'

    @property
    def markdown_source(self):
        page_name = self.kwargs.get('page', '')
        if page_name not in directory_map:
            raise Http404(f'Page "{page_name}" not found.')
        markdown_path = Path(__file__).parent / 'pages' / f'{page_name}.md'
        if not markdown_path.is_file():
            raise Http404(f'Markdown source for page "{page_name}" not found.')
        with open(markdown_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = f'{content}\n\n' \
                  f'Here is the python sample code:\n\n```python\n{self.python_code}\n```\n\n' \
                  f'Here is the assembly example code:\n\n```\n{self.assembly_code}\n```'
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
            'python_code': self.python_code,
            'assembly_code': self.assembly_code,
            'rendered_html': self.rendered_html,
        })
        return super().get_context_data(**kwargs)


class EditorView(PageView):
    template_name = 'assembly_learner/editor.html'
    post = PageView.get
