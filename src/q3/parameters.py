"""建模团队确认的Q3联合实验集合，参考入口与后续搜索共用。"""

from itertools import product

ALPHA_CHOICES = (.80, .85, .90, .95)
LAMBDA_CHOICES = (0., .25, .5, 1., 2.)
PARAMETER_GRID = tuple(product(ALPHA_CHOICES, LAMBDA_CHOICES))
