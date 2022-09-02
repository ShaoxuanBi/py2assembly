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

In ``convert_any``, instances of every ``ast`` classes are assigned by name, to different operation methods.
For example, assigning ``ast. BinOp`` to the ``py2assembly.converter.converter. convert_binop`` method.
The ``BinOp`` identifies a binary operation, and when performing a binary operation, program needs to process the left and right operators separately firstly.
So in ``convert_binop``, the corresponding methods are called on the left and right parts respectively.
Then it goes back to ``convert_binop`` to perform the arithmetic on the left and right parts of the result.

The rest of the syntax modules are explained in detail in every method.

Once all the conversions have been done, the code for ``sigma16`` is obtained.
"""
import ast
import copy
import re
from functools import cached_property
from typing import Dict, Type, Callable, List, Iterable

import attrs



@attrs.define(slots=True)
class ExtraData:                                       # Used to declare various additional parameters (e.g. memory data, registers, etc.) and to determine whether the registers have been used
    memory_data: Dict[str, int] = attrs.Factory(dict)  # memory data, respectively the name and initial value in memory

    locked_registers: Iterable[int] = ()
    """
    In some calculations, some registers may have to be locked to hold some temporary variables.
    """

    target_register: int = -1
    """
    In some operations, it may be necessary to specify in which register the result of a calculation is written, for example when performing continuous operations.     
    Since a unit of memory is not allocated in the program, it is necessary to set up a temporary register for representing the result 
    and this result will also be applied to subsequent operations. 
    The default value is -1, which means that it is not specified.
    """

    if_true_label: str = ''
    if_done_label: str = ''
    """
    Conditional statements require two labels.
    When the conditional statement is true, it jumps to the ``if_true_label`` position for execution and then to the end of the ``if_done_label``.
    If the conditional statement is false, it is executed without skipping, and then jumps to the end of ``if_done_label``.
    There is no need to set an ``if_false_label``, since the statement is executed directly when it is false.
    """

    loop_start_label: str = ''
    """
    The loop statement requires three labels. 
    If the judgement is true, it jumps to ``if_true_label`` for execution and then jumps back to ``while_start_label``. 
    If false, jump to ``if_done_label`` to end the loop.
    """

    def get_available_register(self):
        """Get a register that is not locked and not specified as an output result"""
        for i in range(1, 15):
            if i in self.locked_registers:   # Judge whether the register is in the locked register
                continue
            if i == self.target_register:    # Judge whether a register is present as the output result
                continue
            self.locked_registers = (*self.locked_registers, i)  # When the loop reaches a register that can be used, the sequence i is output
            return i
        else:
            raise NotImplementedError('All registers are already in use.')  # Error reported 'All registers are used prompt' when all registers are detected as unavailable

    def __add__(self, other: 'ExtraData'):   # Logging of all memory data, constantly updated
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
        """A self-constructed conversion module to temporarily store objects which need to be converted"""
        code = []
        extra = ExtraData()   # Create two empty arrays to record the conversion code and additional parameters

        for sub in obj.body:  # Iterate through all the objects that need to be converted and add them to the appropriate arrays for easy documentation
            sub_code, sub_extra = Converter.convert_any(sub, extra)
            code.extend(sub_code)
            extra += sub_extra

        return code, extra

    @staticmethod
    def convert_binop(obj: ast.BinOp, extra: ExtraData = None):
        """"Handling method of binary operations (+, -, *, /)"""
        code = []
        extra = copy.copy(extra)
        if extra.target_register == -1:
            extra.target_register = extra.get_available_register()
        left, op, right = obj.left, obj.op, obj.right         # Set objects between binary operator
        if not isinstance(left, (ast.Name, ast.Constant)):    # Judge whether the left-hand side of an operator is a variable name or a constant
            raise NotImplementedError
        if not isinstance(op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):  # Judge whether an operator is a symbol in addition, subtraction, multiplication or division
            raise NotImplementedError
        if not isinstance(right, (ast.Name, ast.Constant)):            # Judge whether the right-hand side of an operator is a variable name or a constant
            raise NotImplementedError
        left_register, right_register = extra.get_available_register(), extra.get_available_register()   # Get two registers that are not used to store the results of the left and right sides

        if isinstance(left, ast.Name):     # Judge whether the left-hand side of the operator is a variable name or a constant; if it is a variable name, copy the variable from memory to a register with 'load'
            left_value = left.id
            left_command = 'load'
        elif isinstance(left, ast.Constant):  # If it is a constant, initialize the register a value with 'lea'
            left_value = left.value
            left_command = 'lea'
        else:
            raise NotImplementedError
        code.append(Converter.comment(f'{left_command} R{left_register},{left_value}', obj))  # Finally, it is recorded as the form of Sigma 16 assembly statement and stored in a self-built library, e.g. ' load R1,a[R0]  ；R1 ：= a '

        if isinstance(right, ast.Name):   # For the right side, the same judgement as for the left side
            right_value = right.id
            right_command = 'load'
        elif isinstance(right, ast.Constant):
            right_value = right.value
            right_command = 'lea'
        else:
            raise NotImplementedError
        code.append(Converter.comment(f'{right_command} R{right_register},{right_value}', obj))

        if isinstance(op, ast.Add):   # Determine which of addition, subtraction, multiplication or division the operator is
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
        return code, extra            # Finally, it is recorded as the form of Sigma 16 assembly statement and stored in a self-built library, e.g.' add R3,R1,R2 '

    @staticmethod
    def convert_compare(obj: ast.Compare, extra: ExtraData = None):
        """Handling method of comparison operations"""
        extra = copy.copy(extra)
        code = []
        left_register = extra.get_available_register()
        right_register = extra.get_available_register()

        # Handles the left side of the comparison symbol
        if isinstance(obj.left, ast.Name):
            code.append(f'load R{left_register},{obj.left.id}')
        elif isinstance(obj.left, ast.Constant):
            code.append(f'lea R{left_register},{obj.left.value}')
        else:
            raise NotImplementedError(type(obj.left))

        # Handles the right side of the comparison symbol
        if len(obj.comparators) != 1:   # The first step is to judge the number of symbols, which can only be equal to 1, in order to continue the operation
            raise ValueError(f'Only support 1 operator, not "{obj.ops}".')
        comparator = obj.comparators[0]
        if isinstance(comparator, ast.Name):
            code.append(f'load R{right_register},{comparator.id}')
        elif isinstance(comparator, ast.Constant):
            code.append(f'lea R{right_register},{comparator.value}')
        else:
            raise NotImplementedError(type(obj.comparators))

        code.append(f'cmp R{left_register},R{right_register}')  # Finally, it is recorded as the form of Sigma 16 assembly statement and stored in a self-built library, e.g. 'cmp R5,R8'

        # Handling comparison symbols
        if len(obj.ops) != 1:
            raise ValueError(f'Only support 1 operator, not "{obj.ops}".')
        op = obj.ops[0]
        if isinstance(op, ast.Gt):  # Judge the four comparison symbols (>, >=, <. <=)
            code.append(f'jumpgt {extra.if_true_label}')
        elif isinstance(op, ast.GtE):
            code.append(f'jumpge {extra.if_true_label}')
        elif isinstance(op, ast.Lt):
            code.append(f'jumplt {extra.if_true_label}')
        elif isinstance(op, ast.LtE):
            code.append(f'jumple {extra.if_true_label}')
        else:
            raise NotImplementedError(type(op))
        # It is not necessary to define a false tag here, because if it fails, the following is executed directly, i.e. the default is false
        code.append(f'jump {extra.if_done_label}')  # If false, the loop ends directly

        return code, extra

    @staticmethod
    def convert_if(obj: ast.If, extra: ExtraData = None):
        """Handling method of IF statements"""
        code = []
        extra = copy.copy(extra)
        extra.if_true_label = f'true{obj.lineno}'   # Declare the position label to start execution when the conditional statement is true
        extra.if_done_label = f'done{obj.lineno}'   # Declare the end of execution position label
        compare_code, compare_extra = Converter.convert_any(obj.test, extra)   # Parse the test code
        code.extend(compare_code)  # Judgement on the condition of if, e.g. cmp R1,R2 (compare the magnitude of x and y)
        code.append(f'#label {extra.if_true_label}')  # Add the true label to a self-created library, e.g.' jumpge skip[R0] '
        for i in obj.body:   # Execute the code inside the conditional statement
            body_code, body_extra = Converter.convert_any(i, extra)
            code.extend(body_code)
        # For the handling of labels, it is difficult to process them as labels have to be written on the next line, so here labels are directly on a separate line for the label
        # The label is then written to the next line after all the processing is complete
        code.append(f'#label {extra.if_done_label}')  # Add the ending label to a self-created library, e.g.' done ....'
        return code, extra

    @staticmethod
    def convert_assign(obj: ast.Assign, extra: ExtraData = None):
        """Handling method of assignment syntax operations"""
        code = []

        if extra is None:
            extra = ExtraData()

        # Put the target object in the list for inspection
        targets: List[ast.Name] = obj.targets
        for i in targets:
            if not isinstance(i, ast.Name):  # Determine if it is a variable name
                raise NotImplementedError
        left_values = [i.id for i in targets]
        right_value = obj.value

        # If the right value is a constant, determine if it is the initial value, if it is the initial value use 'data', otherwise use the statement
        if isinstance(right_value, ast.Constant):
            constant = right_value.value

            # Only statements with integer values are currently supported for right hand
            if not isinstance(right_value.value, int):
                raise NotImplementedError

            # For constants, if the name does not exist, it is written directly to memory as the initial value; if the name already exists, it overwrites the value in memory
            for variable_name in left_values:
                if variable_name in extra.memory_data:
                    code.append(Converter.comment(f'lea R1,{constant}', obj))
                    code.append(Converter.comment(f'store R1,{variable_name}', obj))  # Finally, it is recorded as the form of Sigma 16 assembly statement and stored in a self-built library, e.g. 'store R1, R[R0]'
                else:
                    extra.memory_data[variable_name] = constant

        # If the right value is an expression, the expression's parsing method is called for the right value and the result of the calculation is then assigned to the memory location of each left value
        elif isinstance(right_value, ast.BinOp):
            sub_code, sub_extra = Converter.convert_binop(right_value, extra)  # Eg 'add R5,R3,R4(R5 = (a+b)+c)'
            code.extend(sub_code)
            for variable_name in left_values:
                code.append(Converter.comment(f'store R{sub_extra.target_register},{variable_name}', obj))    # ' store R5,x[R0]（x := a+b+c）'
                extra.memory_data.setdefault(variable_name, 0)
        else:
            raise NotImplementedError

        return code, extra

    @staticmethod
    def convert_while(obj: ast.While, extra: ExtraData = None):
        """Handling method of while statement operations"""
        # The handling of the while statement could be summarized to the following program logic
        # The loop structure consists of two main elements: the judgement, and the loop body
        # If the judgement is true, the body of the loop is executed; if the judgement is false, the loop structure is jumped out
        # So the loop content could be summarized as follows:
        #   Judgement
        #   Judgement is true: jump to the loop body and, after executing the loop body, jump to the start
        #   Judgement is false: jump to the end of the loop body
        # With the introduction of the label, the logic could be summarized as follows:
        #   Label: start of the loop structure
        #   Judgement
        #   True result jumps to: the body of the loop
        #   Jump to: the end of the loop structure (if the statement is executed without a jump, the judgement is false)
        #   Label: the body of the loop
        #   Statement of the loop body
        #   Statement of the loop body
        #   Statement of the loop body
        #   Jump to: start of the loop structure
        #   Label: end of loop structure
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
        """Handling method of For statement operations"""
        # The for statement is essentially a syntax of the while statement, and all for statements could be implemented with While statements essentially
        # So this algorithm method treats the For statement by converting it to a While statement
        # In fact, it is a python code manipulation that converts the original for loop python code into a while loop python code
        # Python code is then given to the compiler to process through the while statement method
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
            # When the For statement is converted to While statement, it is in fact converted to two syntactic constructs: an assignment statement and the while statement that follows
            # Here the compile function is called on each of the two parts, and the compiled assembly code is then aggregated and returned as the assembly code for the For statement
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
        type_name = type(obj).__name__.lower()     # Sorting all instances of ast
        method_name = f'convert_{type_name}'       # Assign to different handing methods by name
        if not hasattr(Converter, method_name):    # The hasattr() function is used to determine whether the instance object of ast contains the corresponding method name
            raise TypeError(f'No convert method {method_name}')  # Report error 'without this conversion method'
        return getattr(Converter, method_name)(obj, extra)       # The getattr() function returns a method name attribute value

    _method_map: Dict[Type, Callable] = {
        ast.Module: convert_module,
        ast.Assign: convert_assign,
    }

    # Parsing the AST syntax tree to get the parsed code, and some procedural content after parsing
    # The code parsed at this point is still an incomplete code, containing some custom instructions, which need to be transformed to get the final assembly code
    # The extra includes some additional properties, such as which memory variables are used
    @cached_property
    def assembly_code(self):
        """"The main method for code translation"""
        code, extra = self.convert_any(self.ast_tree)
        extra: ExtraData
        # Assembly programs need an explicit end-of-program statement, otherwise the program will keep running all the time
        code.append(Converter.comment('trap R0,R0,R0', comment='stop program'))
        temp = []
        label = ''
        # Handling of predefined instructions
        for i in code:
            # During processing, the label instruction is defined
            # The purpose of this instruction is that label is often used to indicate an end-of-execution position, but the end-of-execution position is the next assembly statement
            # When processing, it is difficult to apply to the next ast structure because the individual python statements are processed independently by the ast
            # Therefore, this predefined label instruction is used for recording, which is then added to the latter assembly statement in the post-processing phase
            match = re.match(r'^#label (.*?)(; .*?)?$', i)
            if match:
                label = match.group(1)
                continue
            temp.append(f'{label:<20}{i}')
            if label:
                label = ''
        code = temp
        code.append('')
        # The process of converting python to assembly language, the definition of variable names is different
        # In python, variable names could be defined when they are used anytime, whereas in assembly, variable names must be fully defined at the beginning
        # During the processing of AST, for similar reasons as above, it is difficult to specify variable names into the final memory during processing, so Extra is used for this purpose
        # Processing could be done using predefined instructions, and then the first assignment instruction is specified as the initial variable name in the post-processing stage
        code.extend(Converter.comment(f'{k} data {v}', indent=-20, comment='initial value')
                    for k, v in extra.memory_data.items())
        return '\n'.join(code)

    def convert(self):
        return self.assembly_code


def convert(python_code):
    return Converter(python_code).convert()
