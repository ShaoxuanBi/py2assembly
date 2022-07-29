"""
The conversion tool of python to Sigma 16 assembly code
============================

This module provides a tool for converting ``Python`` to ``Sigma16`` assembly code.
The general idea is as follows：

First, parsing of ``python`` code is achieved using the ``ast`` module of the ``python`` standard library.

Then, parsing results in code that consists of many layers of syntax trees, converting individual character in the code
into instances of the class ``ast.*``. The ``ast`` module defines a large number of code structures,
for example ``ast. Add`` means that there is a plus sign.

Finally, the rest of the code in this module translates what is obtained from ``ast`` into Sigma16 assembly code.

The main method for code translation is ``py2assembly.converter.converter.assembly_code``.
This method essentially calls ``py2assembly.converter.converter.convert_any``.

在 ``convert_any`` 中，将各个 ``ast`` 的类的实例进行分配，按名称分配给不同的处理方法。
例如，将 ``ast.BinOp`` 分配给了 ``py2assembly.converter.Converter.convert_binop`` 方法。
``BinOp`` 标识的就是一个二元运算，在进行二元运算的时候，首先需要分别对左右的两个运算符进行处理。
因此在 ``convert_binop`` 中，又分别对左右两个部分分别调用了相应的处理方法，
然后再回到 ``convert_binop`` 中，对左右两部分的运算结果进行运算。

其余的语法模块都在下面有相应的详细解释，

完成了全部的转换工作后，就得到了 ``sigma16`` 的代码。
"""
import ast
import copy
import re
from functools import cached_property
from typing import Dict, Type, Callable, List, Iterable

import attrs



@attrs.define(slots=True)
class ExtraData:                                       # 用于声明各种附加参数（如：内存数据，寄存器等），以及对寄存器的判断使用
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

    if_true_label: str = ''
    if_done_label: str = ''
    """
    条件语句需要两个标签。
    条件语句为真时，跳转到 ``if_true_label`` 的位置进行执行，然后再跳转到 ``if_done_label`` 结束；
    条件语句为假时，不跳转，直接执行，然后再跳转 ``if_done_label`` 结束。
    不需要设置一个 ``if_false_label`` ，因为语句为假时直接执行就可以。
    """

    loop_start_label: str = ''
    """
    循环语句需要三个标签。
    判断为真时，跳转到 ``if_true_label`` 的位置进行执行，然后跳回 ``while_start_label``；
    判断为假时，跳转到 ``if_done_label`` 结束循环。
    """

    def get_available_register(self):
        """获取一个没有被锁，也没有指定为输出结果的寄存器。"""
        for i in range(1, 15):
            if i in self.locked_registers:   # 判断是否存在于被锁定的寄存器
                continue
            if i == self.target_register:    # 判断是否存在于作为输出结果的寄存器
                continue
            self.locked_registers = (*self.locked_registers, i)  # 当循环到能用的寄存器，则输出序列i
            return i
        else:
            raise NotImplementedError('All registers are already in use.')  # 当检测到所有的寄存器都不可用时，报错'所有寄存器被使用的提示'

    def __add__(self, other: 'ExtraData'):   # 将所有的内存数据进行记录，不断地更新
        return ExtraData(
            memory_data={**self.memory_data, **other.memory_data}
        )


class Converter:
    def __init__(self, python_code: str):   # Implementing the default constructor
        self.python_code = python_code

    @cached_property
    def ast_tree(self):
        """Parsing the source code into a Parser Tree,then the parser tree is converted into an Abstract Syntax Tree"""
        return ast.parse(self.python_code)

    @staticmethod
    def comment(assembly_code: str, obj: ast.AST = None, comment: str = None, indent=0):
        """Insert python code as comments into assembly code"""
        assert comment is not None or obj is not None, 'Code objects and comments cannot both be None.'
        line_number = '#'
        if comment is None:
            python_code = ast.unparse(obj)   # Make python code unparsed, because to use it to generate comments
            comment = python_code   # Use it as a comment
            line_number = obj.lineno  # Make it the same number of rows on the left and right
        # Since the code section will be indented by 4 spaces, the default total width is 36,
        # which can make the final width 60
        width = 40 - indent
        __keep = (line_number,)
        return f'{assembly_code:<{width}}; {comment}'  # Finally, in the right box of the Sigma 16 assembly language, the generated format of assembly language + width + comments

    # signature of convert methods:
    # def convert_xxx(obj: ast object, extra: dict=None): -> code: list[str], extra: dict
    # The input parameter is the object to be converted and additional data,
    # and the output parameter is the list of converted strings and additional data
    @staticmethod
    def convert_module(obj: ast.Module, extra: ExtraData = None):
        """自建的一个转换模型库，用于记录所有的转换"""
        code = []
        extra = ExtraData()   # 建立两个空的数组，用于记录转换代码和附加参数

        for sub in obj.body:  # 遍历所有的需要被转换的对象，并将其添加到相应的数组中，便于记录
            sub_code, sub_extra = Converter.convert_any(sub, extra)
            code.extend(sub_code)
            extra += sub_extra

        return code, extra

    @staticmethod
    def convert_binop(obj: ast.BinOp, extra: ExtraData = None):
        """"对于二元运算操作（+，-，*，/）的处理方法"""
        code = []
        extra = copy.copy(extra)
        if extra.target_register == -1:
            extra.target_register = extra.get_available_register()
        left, op, right = obj.left, obj.op, obj.right         # Set objects between binary operator
        if not isinstance(left, (ast.Name, ast.Constant)):    # 判断操作符左边的是否是变量名称或常量
            raise NotImplementedError
        if not isinstance(op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):  # 判断操作符是否是加减乘除里的符号
            raise NotImplementedError
        if not isinstance(right, (ast.Name, ast.Constant)):            # 判断操作符右边的是否是变量名称或常量
            raise NotImplementedError
        left_register, right_register = extra.get_available_register(), extra.get_available_register()   # 获取两个没有被使用的寄存器，储存左右两边的结果

        if isinstance(left, ast.Name):     # 判断操作符左边是变量名称还是常量，如果是变量名称，用'load'把变量从内存复制到寄存器
            left_value = left.id
            left_command = 'load'
        elif isinstance(left, ast.Constant):  # 如果是常量，则用'lea'将寄存器进行初始化值
            left_value = left.value
            left_command = 'lea'
        else:
            raise NotImplementedError
        code.append(Converter.comment(f'{left_command} R{left_register},{left_value}', obj))  # 最后，以汇编语句的形式记录在自建的库里进行保存, 如 ' load R1,a[R0]  ；R1 ：= a '

        if isinstance(right, ast.Name):   # 对于右边的判断与左边的一样
            right_value = right.id
            right_command = 'load'
        elif isinstance(right, ast.Constant):
            right_value = right.value
            right_command = 'lea'
        else:
            raise NotImplementedError
        code.append(Converter.comment(f'{right_command} R{right_register},{right_value}', obj))

        if isinstance(op, ast.Add):   # 判断操作符是加法，减法，乘法，除法之中的哪一个
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
        return code, extra                                       # 最后，以汇编语句的形式记录在自建的库里进行保存，如' add R3,R1,R2 '

    @staticmethod
    def convert_compare(obj: ast.Compare, extra: ExtraData = None):
        """对于比较运算符操作的处理方法"""
        extra = copy.copy(extra)
        code = []
        left_register = extra.get_available_register()
        right_register = extra.get_available_register()

        # 处理比较符号的左边
        if isinstance(obj.left, ast.Name):
            code.append(f'load R{left_register},{obj.left.id}')
        elif isinstance(obj.left, ast.Constant):
            code.append(f'lea R{left_register},{obj.left.value}')
        else:
            raise NotImplementedError(type(obj.left))

        # 处理比较符号的右边
        if len(obj.comparators) != 1:   # 首先需要判断判断符号的个数，只能等于1，才能继续操作
            raise ValueError(f'Only support 1 operator, not "{obj.ops}".')
        comparator = obj.comparators[0]
        if isinstance(comparator, ast.Name):
            code.append(f'load R{right_register},{comparator.id}')
        elif isinstance(comparator, ast.Constant):
            code.append(f'lea R{right_register},{comparator.value}')
        else:
            raise NotImplementedError(type(obj.comparators))

        code.append(f'cmp R{left_register},R{right_register}')  # 最后，以汇编语句的形式记录在自建的库里进行保存，如 'cmp R5,R8'

        # 处理比较符号
        if len(obj.ops) != 1:
            raise ValueError(f'Only support 1 operator, not "{obj.ops}".')
        op = obj.ops[0]
        if isinstance(op, ast.Gt):  # 判断四种比较符号（>, >=, <. <=）
            code.append(f'jumpgt {extra.if_true_label}')
        elif isinstance(op, ast.GtE):
            code.append(f'jumpge {extra.if_true_label}')
        elif isinstance(op, ast.Lt):
            code.append(f'jumplt {extra.if_true_label}')
        elif isinstance(op, ast.LtE):
            code.append(f'jumple {extra.if_true_label}')
        else:
            raise NotImplementedError(type(op))
        # 这里不需要定义 false 的标签，因为如果判断失败则直接执行下面的内容，也就是默认走 false
        code.append(f'jump {extra.if_done_label}')  # false的时候，直接结束循环

        return code, extra

    @staticmethod
    def convert_if(obj: ast.If, extra: ExtraData = None):
        """对于if语句操作处理方法"""
        code = []
        extra = copy.copy(extra)
        extra.if_true_label = f'true{obj.lineno}'
        extra.if_done_label = f'done{obj.lineno}'
        compare_code, compare_extra = Converter.convert_any(obj.test, extra)
        code.extend(compare_code)
        code.append(f'#label {extra.if_true_label}')
        for i in obj.body:
            body_code, body_extra = Converter.convert_any(i, extra)
            code.extend(body_code)
        # 对于标签的处理，由于标签要写在下一行中，难以进行处理，因此在这里直接为标签另起一行，
        # 然后在全部处理完成的后处理阶段，再将标签写入下一行。
        code.append(f'#label {extra.if_done_label}')
        return code, extra

    @staticmethod
    def convert_assign(obj: ast.Assign, extra: ExtraData = None):
        """对于赋值语法操作处理方法"""
        code = []

        if extra is None:
            extra = ExtraData()

        # 将目标对象放入列表进行检查
        targets: List[ast.Name] = obj.targets
        for i in targets:
            if not isinstance(i, ast.Name):  # 判断是否是变量名称
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
                    code.append(Converter.comment(f'store R1,{variable_name}', obj))  # 以汇编语句的形式记录在自建的库里进行保存，如 'store R1, R[R0]'
                else:
                    extra.memory_data[variable_name] = constant

        # 如果右值为表达式，则对右值调用表达式的解析方法，然后将过计算结果赋值给各个左值的内存位置
        elif isinstance(right_value, ast.BinOp):
            sub_code, sub_extra = Converter.convert_binop(right_value, extra)  # 如 'add R5,R3,R4(R5 = (a+b)+c)'
            code.extend(sub_code)
            for variable_name in left_values:
                code.append(Converter.comment(f'store R{sub_extra.target_register},{variable_name}', obj))    # 则' store R5,x[R0]（x := a+b+c）'
                extra.memory_data.setdefault(variable_name, 0)
        else:
            raise NotImplementedError

        return code, extra

    @staticmethod
    def convert_while(obj: ast.While, extra: ExtraData = None):
        code = []
        extra = ExtraData() if extra is None else copy.deepcopy(extra)
        extra.loop_start_label = f'loop{obj.lineno}'
        extra.if_true_label = f'true{obj.lineno}'
        extra.if_done_label = f'done{obj.lineno}'

        code.append(f'#label {extra.loop_start_label}')
        test_code, test_extra = Converter.convert_any(obj.test, extra)
        code.extend(test_code)
        code.append(f'#label {extra.if_true_label}')
        for i in obj.body:
            body_code, body_extra = Converter.convert_any(i, extra)
            code.extend(body_code)
        code.append(f'jump {extra.loop_start_label}')
        code.append(f'#label {extra.if_done_label}')
        return code, extra

    @staticmethod
    def convert_for(obj: ast.For, extra: ExtraData = None):
        code = []
        extra = ExtraData() if extra is None else copy.deepcopy(extra)
        if isinstance(obj.iter, ast.Call) and obj.iter.func.id == 'range':
            if not len(obj.iter.args) == 2:
                raise ValueError('Only supports range with 2 parameters')
            start, end = obj.iter.args
            start, end = start.value, end.value
            target = obj.target.id
            while_code = f'''{target} = {start}\nwhile {target} < {end}:\n    {target} = {target} + 1'''
            while_code = ast.parse(while_code)
            assign_obj, while_obj = while_code.body
            assign_obj: ast.Assign
            while_obj: ast.While
            assign_obj.lineno = obj.lineno
            while_obj.lineno = obj.lineno
            last_line = while_obj.body.pop(-1)
            while_obj.body.extend(obj.body)
            while_obj.body.append(last_line)
            assign_code, assign_extra = Converter.convert_any(assign_obj, extra)
            while_code, while_extra = Converter.convert_any(while_obj, extra)
            code.extend(assign_code)
            code.extend(while_code)
        else:
            raise NotImplementedError(type(obj.iter))
        return code, extra

    @staticmethod
    def convert_any(obj, extra: ExtraData = None) -> (List[str], ExtraData):
        type_name = type(obj).__name__.lower()     # 将所有ast的实例进行分类
        method_name = f'convert_{type_name}'       # 按名称分配给不同的处理方法
        if not hasattr(Converter, method_name):    # hasattr() 函数用于判断ast的实例对象是否包含对应的方法名称
            raise TypeError(f'No convert method {method_name}')  # 报错没有此转换方法的提示
        return getattr(Converter, method_name)(obj, extra)       # getattr() 函数返回一个方法名称属性值

    _method_map: Dict[Type, Callable] = {
        ast.Module: convert_module,
        ast.Assign: convert_assign,
    }

    @cached_property
    def assembly_code(self):
        """"The main method for code translation"""
        code, extra = self.convert_any(self.ast_tree)  #将由源代码解析之后变成的语法树作为参数，分配不同的方法
        extra: ExtraData
        code.append(Converter.comment('trap R0,R0,R0', comment='stop program'))  # 在每个方法结尾处，添加这一行注释，表示翻译结束
        temp = []
        label = ''
        for i in code:
            match = re.match(r'^#label (.*?)(; .*?)?$', i)
            if match:
                label = match.group(1)
                continue
            temp.append(f'{label:<20}{i}')
            if label:
                label = ''
        code = temp
        code.append('')
        code.extend(Converter.comment(f'{k} data {v}', indent=-20, comment='initial value')
                    for k, v in extra.memory_data.items())
        return '\n'.join(code)

    def convert(self):
        return self.assembly_code


def convert(python_code):
    return Converter(python_code).convert()
