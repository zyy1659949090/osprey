from __future__ import print_function, absolute_import, division
"""searchspace.py

This module contains code for specifying the hyperparameter search space.
The search space is specified as a product of bounded intervals. Each dimension
can be either an integer, floating-point or enumeration.

The base measure on the space, e.g. for random sampling (`rvs()`) is a product
of uniform distribution on the bounded intervals. This can, however, be
modified for floating-point dimensions using the `warp` keyword argument in
`add_float`
"""
from collections import namedtuple, Iterable

import numpy as np
from sklearn.utils import check_random_state
try:
    from hyperopt import hp, pyll
except ImportError:
    from .utils import mock_module
    hp = mock_module('hyperopt')
    pyll = mock_module('hyperopt')


class SearchSpace(object):
    def __init__(self):
        self.variables = {}

    @property
    def n_dims(self):
        return len(self.variables)

    def add_jump(self, name, min, max, num, warp=None, var_type=float):
        """ An integer/float-valued enumerable with `num` items, bounded
        between [`min`, `max`]. Note that the right endpoint of the interval
        includes `max`. This is a wrapper around the add_enum. `jump` can be
        a float or int.
        """
        if not isinstance(var_type, type):
            if var_type == 'int':
                var_type = int
            elif var_type == 'float':
                var_type = float
            else:
                raise ValueError('var_type (%s) is not supported. use '
                                 '"int" or "float",' % (var_type))

        min, max = map(var_type, (min, max))
        num = int(num)

        if not warp:
            choices = np.linspace(min, max, num=num, dtype=var_type)
        elif (min >= 0) and warp == 'log':
            choices = np.logspace(np.log10(min), np.log10(max), num=num,
                                  dtype=var_type)
        elif (min <= 0)and warp == 'log':
            raise ValueError('variable %s: log-warping requires min > 0')
        else:
            raise ValueError('variable %s: warp=%s is not supported. use '
                             'None or "log",' % (name, warp))

        self.variables[name] = EnumVariable(name, choices.tolist())

    def add_int(self, name, min, max, warp=None):
        """An integer-valued dimension bounded between `min` <= x <= `max`.
        Note that the right endpoint of the interval includes `max`.

        When `warp` is None, the base measure associated with this dimension
        is a categorical distribution with each weight on each of the integers
        in [min, max]. With `warp == 'log'`, the base measure is a uniform
        distribution on the log of the variable, with bounds at `log(min)` and
        `log(max)`. This is appropriate for variables that are "naturally" in
        log-space. Other `warp` functions are not supported (yet), but may be
        at a later time. Please note that this functionality is not supported
        for `hyperopt_tpe`.
        """
        min, max = map(int, (min, max))
        if max < min:
            raise ValueError('variable %s: max < min error' % name)
        if warp not in (None, 'log'):
            raise ValueError('variable %s: warp=%s is not supported. use '
                             'None or "log",' % (name, warp))
        if min <= 0 and warp == 'log':
            raise ValueError('variable %s: log-warping requires min > 0')

        self.variables[name] = IntVariable(name, min, max, warp)

    def add_float(self, name, min, max, warp=None):
        """A floating point-valued dimension bounded `min` <= x < `max`

        When `warp` is None, the base measure associated with this dimension
        is a uniform distribution on [min, max). With `warp == 'log'`, the
        base measure is a uniform distribution on the log of the variable,
        with bounds at `log(min)` and `log(max)`. This is appropriate for
        variables that are "naturally" in log-space. Other `warp` functions
        are not supported (yet), but may be at a later time.
        """
        min, max = map(float, (min, max))
        if not min < max:
            raise ValueError('variable %s: min >= max error' % name)
        if warp not in (None, 'log'):
            raise ValueError('variable %s: warp=%s is not supported. use '
                             'None or "log",' % (name, warp))
        if min <= 0 and warp == 'log':
            raise ValueError('variable %s: log-warping requires min > 0')

        self.variables[name] = FloatVariable(name, min, max, warp)

    def add_enum(self, name, choices):
        """An enumeration-valued dimension.

        The base measure associated with this dimension is a categorical
        distribution with equal weight on each element in `choices`.
        """
        if not isinstance(choices, Iterable):
            raise ValueError('variable %s: choices must be iterable' % name)
        self.variables[name] = EnumVariable(name, choices)

    def __getitem__(self, name):
        return self.variables[name]

    def __iter__(self):
        return iter(self.variables.values())

    def rvs(self, seed=None):
        random = check_random_state(seed)
        return dict((param.name, param.rvs(random)) for param in self)

    def to_hyperopt(self):
        return dict((v.name, v.to_hyperopt()) for v in self)

    def point_to_gp(self, point_dict):
        return [var.point_to_gp(point_dict[var.name]) for var in self]

    def __repr__(self):
        lines = (['Hyperparameter search space:'] +
                 ['  ' + repr(var) for var in self])
        return '\n'.join(lines)


class IntVariable(namedtuple('IntVariable', ('name', 'min', 'max', 'warp'))):
    # this pattern is a simple memory-efficient way to add some methods to
    # a namedtuple, demonstrated in sklearn.
    # https://github.com/scikit-learn/scikit-learn/blob/a38372998b560d184a195bbd10a16c8f20119aa8/sklearn/grid_search.py#L259-L278

    __slots__ = ()

    def __repr__(self):
        return '{0:<25s}\t(int)   {1:8d} <= x <= {2:d}'.format(
            self.name, self.min, self.max)

    def rvs(self, random):
        # extra +1 here because of the _inclusive_ endpoint
        if self.warp is None:
            return random.randint(self.min, self.max+1)
        elif self.warp == 'log':
            return int(np.exp(random.uniform(np.log(self.min), np.log(self.max+1))))
        raise ValueError('unknown warp: %s' % self.warp)

    def to_hyperopt(self):
        if self.warp is None:
            return pyll.scope.int(hp.uniform(self.name, self.min, self.max+1))
        raise ValueError('warped integers are not supported for hyperopt')

    def domain_to_gp(self):
        return {'min': 0.0, 'max': 1.0}

    def point_to_gp(self, value):
        if self.warp is None:
            return (value - self.min) / (self.max - self.min)
        elif self.warp == 'log':
            rng = np.log(self.max) - np.log(self.min)
            return int((np.log(value) - np.log(self.min)) / rng)

        raise ValueError('unknown warp: %s' % self.warp)

    def point_from_gp(self, gpvalue):
        if self.warp is None:
            return int(np.floor(min(self.min + gpvalue * (self.max - self.min + 1), self.max)))
        elif self.warp == 'log':
            rng = np.log(self.max+1) - np.log(self.min)
            outvalue = np.exp(np.log(self.min) + gpvalue * rng)
            return np.clip(outvalue, self.min, self.max).astype(int)
        raise ValueError('unknown warp: %s' % self.warp)


class FloatVariable(namedtuple('FloatVariable',
                               ('name', 'min', 'max', 'warp'))):
    __slots__ = ()

    def __repr__(self):
        return '{0:<25s}\t(float) {1:8f} <= x <  {2:f}'.format(
            self.name, self.min, self.max)

    def rvs(self, random):
        if self.warp is None:
            return random.uniform(self.min, self.max)
        elif self.warp == 'log':
            return np.exp(random.uniform(np.log(self.min), np.log(self.max)))
        raise ValueError('unknown warp: %s' % self.warp)

    def to_hyperopt(self):
        if self.warp is None:
            return hp.uniform(self.name, self.min, self.max)
        elif self.warp == 'log':
            return hp.loguniform(self.name, np.log(self.min), np.log(self.max))
        raise ValueError('unknown warp: %s' % self.warp)

    def domain_to_gp(self):
        return {'min': 0.0, 'max': 1.0}

    def point_to_gp(self, value):
        if self.warp is None:
            return (value - self.min) / (self.max - self.min)
        elif self.warp == 'log':
            rng = np.log(self.max) - np.log(self.min)
            return (np.log(value) - np.log(self.min)) / rng

        raise ValueError('unknown warp: %s' % self.warp)

    def point_from_gp(self, gpvalue):
        if self.warp is None:
            outvalue = self.min + (gpvalue * (self.max - self.min))
        elif self.warp == 'log':
            rng = np.log(self.max) - np.log(self.min)
            outvalue = np.exp(np.log(self.min) + gpvalue * rng)
        else:
            raise ValueError('unknown warp: %s' % self.warp)

        return np.clip(outvalue, self.min, self.max)


class EnumVariable(namedtuple('EnumVariable', ('name', 'choices'))):
    __slots__ = ()

    def __repr__(self):
        c = [str(e) for e in self.choices]
        return '{0:<25s}\t(enum)    choices = ({1:s})'.format(
            self.name, ', '.join(c))

    def rvs(self, random):
        return self.choices[random.randint(len(self.choices))]

    def to_hyperopt(self):
        return hp.choice(self.name, self.choices)

    def domain_to_gp(self):
        return {'min': 0.0, 'max': 1.0}

    def point_to_gp(self, value):
        try:
            index = next(i for i, c in enumerate(self.choices) if c == value)
        except StopIteration:
            raise ValueError('%s not in %s' % (value, self.choices))
        return float(index) / max(len(self.choices) - 1, 1)

    def point_from_gp(self, gpvalue):
        return self.choices[int(np.round(gpvalue * max(len(self.choices) - 1, 1)))]
