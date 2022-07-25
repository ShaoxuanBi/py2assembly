import ast
import copy
import attrs
from functools import cached_property
from typing import Dict, Type, Callable, List, Iterable
"""
This module provides tools for converting Python to Sigma16 assembly code.

The general idea is:
First, parsing of ``python`` code is achieved using the ``ast`` module of the ``python`` standard library. 

Then, parsing results in code that consists of many layers of syntax trees, converting individual character in the code 
into instances of the class ``ast.*``. The ``ast`` module defines a large number of code structures, for example ``ast. Add`` means that there is a plus sign. 

Finally, the rest of the code in this module translates the contents obtained by ``ast`` into assembly code. 

The main method for code translation is ``py2assembly.converter.converter.assembly_code``. 
This method essentially calls ``py2assembly.converter.converter.convert_any``. 
In ``convert_any``, instances of each ``ast`` class are assigned, by name, to different handlers. 
For example, ``ast. BinOp`` is assigned to the ``py2assembly.converter.converter. convert_binop`` method. 
The ``BinOp`` identifies a binary operation, and when performing a binary operation, you first need to process the left and right operators separately. 
So in ``convert_binop``, the corresponding methods are called on the left and right parts respectively. 
Then you go back to ``convert_binop`` and do the arithmetic on the left and right parts. 

Once the conversion is complete, the code for ``sigma16`` is obtained.
"""

@attrs.define(slots=True)
class ExtraData:
    memory_data: Dict[str, int] = attrs.Factory(dict)  # 内存数据，分别是内存中的名称和初值

    locked_registers: Iterable[int] = ()
    """
    在一些计算中，可能要锁定一些寄存器，以保存一些临时变量。
    """

    target_register: int = -1
    """
    在一些操作中，可能需要指定计算后的结果写在哪个寄存器中，例如在进行连续运算的时候，
    由于程序中没有分配一个内存单位，因此需要设置一个临时的寄存器用于表示结果，
    而这个结果还将应用到后续的运算中。
    默认值为-1，表示没有指定。
    """

    def get_available_register(self):
        """获取一个没有被锁，也没有指定为输出结果的寄存器。"""
        for i in range(1, 15):
            if i in self.locked_registers:
                continue
            if i == self.target_register:
                continue
            self.locked_registers = (*self.locked_registers, i)
            return i
        else:
            raise NotImplementedError('All registers are already in use.')

    def __add__(self, other: 'ExtraData'):
        return ExtraData(
            memory_data={**self.memory_data, **other.memory_data}
        )


class Converter:
    def __init__(self, python_code: str):
        self.python_code = python_code

    @cached_property
    def ast_tree(self):
        return ast.parse(self.python_code)

    @staticmethod
    def comment(assembly_code: str, obj: ast.AST = None, comment: str = None, indent=0):
        """Insert python code as comments into assembly code"""
        assert comment is not None or obj is not None, 'Code objects and comments cannot both be None.'
        line_number = '#'
        if comment is None:
            python_code = ast.unparse(obj)
            comment = python_code
            line_number = obj.lineno
        # Since the code section will be indented by 4 spaces, the default total width is 36,
        # which can make the final width 40
        width = 36 - indent
        __keep = (line_number,)
        return f'{assembly_code:<{width}}; {comment}'

    # signature of convert methods:
    # def convert_xxx(obj: ast object, extra: dict=None): -> code: list[str], extra: dict
    #     The input parameter is the object to be converted and additional data, and the output parameter is the list of
    #     converted strings and additional data
    @staticmethod
    def convert_module(obj: ast.Module, extra: ExtraData = None):
        code = []
        extra = ExtraData()

        for sub in obj.body:
            sub_code, sub_extra = Converter.convert_any(sub, extra)
            code.extend(sub_code)
            extra += sub_extra

        return code, extra

    @staticmethod
    def convert_binop(obj: ast.BinOp, extra: ExtraData = None):
        code = []
        extra = copy.copy(extra)
        if extra.target_register == -1:
            extra.target_register = extra.get_available_register()
        left, op, right = obj.left, obj.op, obj.right
        if not isinstance(left, (ast.Name, ast.Constant)):
            raise NotImplementedError
        if not isinstance(op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            raise NotImplementedError
        if not isinstance(right, (ast.Name, ast.Constant)):
            raise NotImplementedError
        left_register, right_register = extra.get_available_register(), extra.get_available_register()

        if isinstance(left, ast.Name):
            left_value = left.id
            left_command = 'load'
        elif isinstance(left, ast.Constant):
            left_value = left.value
            left_command = 'lea'
        else:
            raise NotImplementedError
        code.append(Converter.comment(f'{left_command} R{left_register},{left_value}', obj))

        if isinstance(right, ast.Name):
            right_value = right.id
            right_command = 'load'
        elif isinstance(right, ast.Constant):
            right_value = right.value
            right_command = 'lea'
        else:
            raise NotImplementedError
        code.append(Converter.comment(f'{right_command} R{right_register},{right_value}', obj))

        if isinstance(op, ast.Add):
            operator = 'add'
        elif isinstance(op, ast.Sub):
            operator = 'sub'
        elif isinstance(op, ast.Mult):
            operator = 'mul'
        elif isinstance(op, ast.Div):
            operator = 'div'
        else:
            raise NotImplementedError
        code.append(Converter.comment(f'{operator} R{extra.target_register},R{left_register},R{right_register}', obj))
        return code, extra

    @staticmethod
    def convert_assign(obj: ast.Assign, extra: ExtraData = None):
        code = []

        if extra is None:
            extra = ExtraData()

        # noinspection PyTypeChecker
        targets: List[ast.Name] = obj.targets
        for i in targets:
            if not isinstance(i, ast.Name):
                raise NotImplementedError
        left_values = [i.id for i in targets]
        right_value = obj.value

        # 如果右值为常量，则判断是否是初值，如果是初值则使用data，否则使用语句
        if isinstance(right_value, ast.Constant):
            constant = right_value.value

            # 目前仅支持处理右值为整数的语句
            if not isinstance(right_value.value, int):
                raise NotImplementedError

            # 对于常量，如果命名不存在，则直接写入内存作为初值；如果命名已存在，则覆盖内存中的值
            for variable_name in left_values:
                if variable_name in extra.memory_data:
                    code.append(Converter.comment(f'lea R1,{constant}', obj))
                    code.append(Converter.comment(f'store R1,{variable_name}', obj))
                else:
                    extra.memory_data[variable_name] = constant

        # 如果右值为表达式，则对右值调用表达式的解析方法，然后将过计算结果赋值给各个左值的内存位置
        elif isinstance(right_value, ast.BinOp):
            sub_code, sub_extra = Converter.convert_binop(right_value, extra)
            code.extend(sub_code)
            for variable_name in left_values:
                code.append(Converter.comment(f'store R{sub_extra.target_register},{variable_name}', obj))
                extra.memory_data.setdefault(variable_name, 0)
        else:
            raise NotImplementedError

        return code, extra

    @staticmethod
    def convert_any(obj, extra: ExtraData = None) -> (List[str], ExtraData):
        type_name = type(obj).__name__.lower()
        method_name = f'convert_{type_name}'
        if not hasattr(Converter, method_name):
            raise TypeError(f'No convert method {method_name}')
        return getattr(Converter, method_name)(obj, extra)

    _method_map: Dict[Type, Callable] = {
        ast.Module: convert_module,
        ast.Assign: convert_assign,
    }

    @cached_property
    def assembly_code(self):
        code, extra = self.convert_any(self.ast_tree)
        extra: ExtraData
        code.append(Converter.comment('trap R0,R0,R0', comment='stop program'))
        code = [f'    {i}' for i in code]
        code.append('')
        code.extend(Converter.comment(f'{k} data {v}', indent=-4, comment='initial value')
                    for k, v in extra.memory_data.items())
        return '\n'.join(code)

    def convert(self):
        return self.assembly_code


def convert(python_code):
    return Converter(python_code).convert()
