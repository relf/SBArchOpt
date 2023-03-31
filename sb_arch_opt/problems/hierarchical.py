"""
Licensed under the GNU General Public License, Version 3.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.gnu.org/licenses/gpl-3.0.html.en

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Copyright: (c) 2023, Deutsches Zentrum fuer Luft- und Raumfahrt e.V.
Contact: jasper.bussemaker@dlr.de

This test suite contains a set of mixed-discrete, constrained, hierarchical, multi-objective problems.
"""
import enum
import itertools
import numpy as np
from typing import *
from deprecated import deprecated
from scipy.spatial import distance
from sb_arch_opt.sampling import *
from pymoo.problems.multi.zdt import ZDT1
from sb_arch_opt.problems.discrete import *
from sb_arch_opt.problems.problems_base import *
from pymoo.problems.multi.omnitest import OmniTest
from pymoo.core.variable import Real, Integer, Choice
from pymoo.util.ref_dirs import get_reference_directions

__all__ = ['HierarchyProblemBase', 'HierarchicalGoldstein', 'HierarchicalRosenbrock', 'ZaeffererHierarchical',
           'ZaeffererProblemMode', 'MOHierarchicalGoldstein', 'MOHierarchicalRosenbrock', 'HierarchicalMetaProblemBase',
           'MOHierarchicalTestProblem', 'Jenatton', 'TunableHierarchicalMetaProblem', 'TunableZDT1', 'HierZDT1',
           'HierZDT1Small', 'HierZDT1Large', 'HierDiscreteZDT1', 'HierBranin']


class HierarchyProblemBase(ArchOptTestProblemBase):
    """Base class for test problems that have decision hierarchy"""

    def _get_n_valid_discrete(self) -> int:
        raise NotImplementedError

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class HierarchicalGoldstein(HierarchyProblemBase):
    """
    Variable-size design space Goldstein function from:
    Pelamatti 2020: "Bayesian Optimization of Variable-Size Design Space Problems", section 5.2 and Appendix B

    Properties:
    - 5 continuous variables
    - 4 integer variables
    - 2 categorical variables
    - Depending on the categorical variables, 8 different sub-problems are defined, ranging from 2 cont + 4 integer to
      5 cont + 2 integer variables
    - 1 objective, 1 constraint
    """

    _mo = False

    def __init__(self):
        des_vars = [
            Real(bounds=(0, 100)), Real(bounds=(0, 100)), Real(bounds=(0, 100)), Real(bounds=(0, 100)),
            Real(bounds=(0, 100)),
            Integer(bounds=(0, 2)), Integer(bounds=(0, 2)), Integer(bounds=(0, 2)), Integer(bounds=(0, 2)),
            Choice(options=[0, 1, 2, 3]), Choice(options=[0, 1]),
        ]

        n_obj = 2 if self._mo else 1
        super().__init__(des_vars, n_obj=n_obj, n_ieq_constr=1)

    def _get_n_valid_discrete(self) -> int:
        # w1 and w2 determine activeness, and we can ignore continuous dimensions
        n_valid = np.ones((4, 2), dtype=int)  # w1, w2

        # DV 5 is valid when w1 == 0 or w1 == 2
        n_valid[[0, 2], :] *= 3

        # DV6 is valid when w1 <= 1
        n_valid[:2, :] *= 3

        # DV 7 and 8 are always valid
        n_valid *= 3*3

        return int(np.sum(n_valid))

    def _arch_evaluate(self, x: np.ndarray, is_active_out: np.ndarray, f_out: np.ndarray, g_out: np.ndarray,
                       h_out: np.ndarray, *args, **kwargs):
        self._correct_x_impute(x, is_active_out)
        f_h_map = self._map_f_h()
        g_map = self._map_g()

        for i in range(x.shape[0]):
            x_i = x[i, :5]
            z_i = np.array([int(z) for z in x[i, 5:9]])
            w_i = np.array([int(w) for w in x[i, 9:]])

            f_idx = int(w_i[0]+w_i[1]*4)
            f_out[i, 0] = self.h(*f_h_map[f_idx](x_i, z_i))
            if self._mo:
                f2 = self.h(*f_h_map[f_idx](x_i+30, z_i))+(f_idx/7.)*5
                f_out[i, 1] = f2

            g_idx = int(w_i[0])
            g_out[i, 0] = self.g(*g_map[g_idx](x_i, z_i))

    def _correct_x(self, x: np.ndarray, is_active: np.ndarray):
        w1 = x[:, 9].astype(int)
        w2 = x[:, 10].astype(int)

        is_active[:, 2] = (w1 == 1) | (w1 == 3)  # x3
        is_active[:, 3] = w1 >= 2  # x4
        is_active[:, 4] = w2 == 1  # x5

        is_active[:, 5] = (w1 == 0) | (w1 == 2)  # z1
        is_active[:, 6] = w1 <= 1  # z2

    @staticmethod
    def h(x1, x2, x3, x4, x5, z3, z4, cos_term: bool) -> float:
        h = MDGoldstein.h(x1, x2, x3, x4, z3, z4)
        if cos_term:
            h += 5.*np.cos(2.*np.pi*(x5/100.))-2.
        return h

    @staticmethod
    def _map_f_h() -> List[Callable[[np.ndarray, np.ndarray], tuple]]:

        # Appendix B, Table 6-11
        _x3 = [20, 50, 80]
        _x4 = [20, 50, 80]

        def _f1(x, z):
            return x[0], x[1], _x3[z[0]], _x4[z[1]], x[4], z[2], z[3], False

        def _f2(x, z):
            return x[0], x[1], x[2],      _x4[z[1]], x[4], z[2], z[3], False

        def _f3(x, z):
            return x[0], x[1], _x3[z[0]], x[3],      x[4], z[2], z[3], False

        def _f4(x, z):
            return x[0], x[1], x[2],      x[3],      x[4], z[2], z[3], False

        def _f5(x, z):
            return x[0], x[1], _x3[z[0]], _x4[z[1]], x[4], z[2], z[3], True

        def _f6(x, z):
            return x[0], x[1], x[2],      _x4[z[1]], x[4], z[2], z[3], True

        def _f7(x, z):
            return x[0], x[1], _x3[z[0]], x[3],      x[4], z[2], z[3], True

        def _f8(x, z):
            return x[0], x[1], x[2],      x[3],      x[4], z[2], z[3], True

        return [_f1, _f2, _f3, _f4, _f5, _f6, _f7, _f8]

    @staticmethod
    def g(x1, x2, c1, c2):
        return -(x1-50.)**2. - (x2-50.)**2. + (20.+c1*c2)**2.

    @staticmethod
    def _map_g() -> List[Callable[[np.ndarray, np.ndarray], tuple]]:

        # Appendix B, Table 12-15
        _c1 = [3., 2., 1.]
        _c2 = [.5, -1., -2.]

        def _g1(x, z):
            return x[0], x[1], _c1[z[0]], _c2[z[1]]

        def _g2(x, z):
            return x[0], x[1], .5,        _c2[z[1]]

        def _g3(x, z):
            return x[0], x[1], _c1[z[0]], .7

        def _g4(x, z):
            return x[0], x[1], _c1[z[2]], _c2[z[3]]

        return [_g1, _g2, _g3, _g4]

    @classmethod
    def validate_ranges(cls, n_samples=5000, show=True):
        """Compare to Pelamatti 2020, Fig. 6"""
        import matplotlib.pyplot as plt
        from sb_arch_opt.sampling import HierarchicalLatinHypercubeSampling

        problem = cls()
        x = HierarchicalLatinHypercubeSampling().do(problem, n_samples).get('X')

        f, g = problem.evaluate(x)
        i_feasible = np.max(g, axis=1) <= 0.

        x_plt, y_plt = [], []
        for i in np.where(i_feasible)[0]:
            w_i = [int(w) for w in x[i, 9:]]
            f_idx = int(w_i[0]+w_i[1]*4)

            x_plt.append(f_idx)
            y_plt.append(f[i])

        plt.figure()
        plt.scatter(x_plt, y_plt, s=1)
        plt.xlabel('Sub-problem'), plt.ylabel('Feasible objective values')

        if show:
            plt.show()


class MOHierarchicalGoldstein(HierarchicalGoldstein):
    """
    Multi-objective adaptation of the hierarchical Goldstein problem. The Pareto front consists of a mix of SP6 and SP8,
    however it is difficult to get a consistent result with NSGA2.

    See Pelamatti 2020 Fig. 6 to compare. Colors in plot of run_test match colors of figure.
    """

    _mo = True

    @classmethod
    def run_test(cls):
        from pymoo.optimize import minimize
        from pymoo.algorithms.moo.nsga2 import NSGA2
        from pymoo.visualization.scatter import Scatter

        res = minimize(cls(), NSGA2(pop_size=200), termination=('n_gen', 200))
        w_idx = res.X[:, 9] + res.X[:, 10] * 4
        Scatter().add(res.F, c=w_idx, cmap='tab10', vmin=0, vmax=10, color=None).show()


class HierarchicalRosenbrock(HierarchyProblemBase):
    """
    Variable-size design space Rosenbrock function from:
    Pelamatti 2020: "Bayesian Optimization of Variable-Size Design Space Problems", section 5.3 and Appendix C

    Properties:
    - 8 continuous variables
    - 3 integer variables
    - 2 categorical variables
    - Depending on the categorical variables, 4 different sub-problems are defined
    - 1 objective, 2 constraints

    To validate, use so_run() and compare to Pelamatti 2020, Fig. 14
    """

    _mo = False  # Multi-objective

    def __init__(self):
        des_vars = [
            Real(bounds=(-1, .5)), Real(bounds=(0, 1.5)),
            Real(bounds=(-1, .5)), Real(bounds=(0, 1.5)),
            Real(bounds=(-1, .5)), Real(bounds=(0, 1.5)),
            Real(bounds=(-1, .5)), Real(bounds=(0, 1.5)),
            Integer(bounds=(0, 1)), Integer(bounds=(0, 1)), Integer(bounds=(0, 2)),
            Choice(options=[0, 1]), Choice(options=[0, 1]),
        ]

        n_obj = 2 if self._mo else 1
        super().__init__(des_vars, n_obj=n_obj, n_constr=2)

    def _get_n_valid_discrete(self) -> int:
        n_valid = np.ones((2, 2), dtype=int)*2*2  # w1, w2 for DV 8 and 9
        n_valid[:, 1] *= 3  # DV 10 is active when w2 == 1
        return int(np.sum(n_valid))

    def _arch_evaluate(self, x: np.ndarray, is_active_out: np.ndarray, f_out: np.ndarray, g_out: np.ndarray,
                       h_out: np.ndarray, *args, **kwargs):
        self._correct_x_impute(x, is_active_out)
        self._eval_f_g(x, f_out, g_out)

    @classmethod
    def _eval_f_g(cls, x: np.ndarray, f_out: np.ndarray, g: np.ndarray):
        a1 = [7, 7, 10, 10]
        a2 = [9, 6, 9, 6]
        add_z3 = [False, True, False, True]
        x_idx = [[0, 1, 2, 3], [0, 1, 4, 5], [0, 1, 2, 3, 6, 7], [0, 1, 4, 5, 6, 7]]
        x_idx_g2 = [[0, 1, 2, 3], [0, 1, 2, 3, 6, 7]]

        for i in range(x.shape[0]):
            x_i = x[i, :8]
            z_i = [int(z) for z in x[i, 8:11]]

            w_i = [int(w) for w in x[i, 11:]]
            idx = int(w_i[0]*2+w_i[1])

            x_fg = x_i[x_idx[idx]]
            f_out[i, 0] = f1 = cls.f(x_fg, z_i[0], z_i[1], z_i[2], a1[idx], a2[idx], add_z3[idx])
            if cls._mo:
                f2 = abs((400-f1)/40)**2 + np.sum((x_fg[:4]+1)**2*200)
                f_out[i, 1] = f2

            g[i, 0] = cls.g1(x_fg)
            g[i, 1] = cls.g2(x_i[x_idx_g2[idx]]) if idx < 2 else 0.

    def _correct_x(self, x: np.ndarray, is_active: np.ndarray):
        w1 = x[:, 11].astype(int)
        w2 = x[:, 12].astype(int)
        idx = w1*2+w2

        is_active[:, 2] = idx <= 2  # x3
        is_active[:, 3] = idx <= 2  # x4
        is_active[:, 4] = w2 == 1  # x5
        is_active[:, 5] = w2 == 1  # x6
        is_active[:, 6] = idx >= 1  # x7
        is_active[:, 7] = idx >= 1  # x8

        is_active[:, 10] = w2 == 1  # z3

    @staticmethod
    def f(x: np.ndarray, z1, z2, z3, a1, a2, add_z3: bool):
        s = 1. if z2 == 0 else -1.
        pre = 1. if z2 == 0 else .7

        xi, xi1 = x[:-1], x[1:]
        sum_term = np.sum(pre*a1*a2*(xi1-xi)**2 + ((a1+s*a2)/10.)*(1-xi)**2)
        f = 100.*z1 + sum_term
        if add_z3:
            f -= 35.*z3
        return f

    @staticmethod
    def g1(x: np.ndarray):
        xi, xi1 = x[:-1], x[1:]
        return np.sum(-(xi-1)**3 + xi1 - 2.6)

    @staticmethod
    def g2(x: np.ndarray):
        xi, xi1 = x[:-1], x[1:]
        return np.sum(-xi - xi1 + .4)

    @classmethod
    def validate_ranges(cls, n_samples=5000, show=True):
        """Compare to Pelamatti 2020, Fig. 13"""
        import matplotlib.pyplot as plt
        from sb_arch_opt.sampling import HierarchicalLatinHypercubeSampling

        problem = cls()
        x = HierarchicalLatinHypercubeSampling().do(problem, n_samples).get('X')

        f, g = problem.evaluate(x)
        i_feasible = np.max(g, axis=1) <= 0.

        x_plt, y_plt = [], []
        for i in np.where(i_feasible)[0]:
            w_i = [int(w) for w in x[i, 11:]]
            f_idx = int(w_i[0]*2+w_i[1])

            x_plt.append(f_idx)
            y_plt.append(f[i])

        plt.figure()
        plt.scatter(x_plt, y_plt, s=1)
        plt.xlabel('Sub-problem'), plt.ylabel('Feasible objective values')

        if show:
            plt.show()


class MOHierarchicalRosenbrock(HierarchicalRosenbrock):
    """
    Multi-objective adaptation of the hierarchical Rosenbrock problem.

    See Pelamatti 2020 Fig. 13 to compare. Colors in plot of run_test match colors of figure.
    """

    _mo = True

    @classmethod
    def run_test(cls, show=True):
        from pymoo.optimize import minimize
        from pymoo.algorithms.moo.nsga2 import NSGA2

        res = minimize(cls(), NSGA2(pop_size=200), termination=('n_gen', 200))
        w_idx = res.X[:, 11]*2 + res.X[:, 12]
        HierarchicalMetaProblemBase.plot_sub_problems(w_idx, res.F, show=show)


class ZaeffererProblemMode(enum.Enum):
    A_OPT_INACT_IMP_PROF_UNI = 'A'
    B_OPT_INACT_IMP_UNPR_UNI = 'B'
    C_OPT_ACT_IMP_PROF_BI = 'C'
    D_OPT_ACT_IMP_UNPR_BI = 'D'
    E_OPT_DIS_IMP_UNPR_BI = 'E'


class ZaeffererHierarchical(HierarchyProblemBase):
    """
    Hierarchical test function from:
    Zaefferer 2018: "A First Analysis of Kernels for Kriging-Based Optimization in Hierarchical Search Spaces",
      section 5
    """

    _mode_map = {
        ZaeffererProblemMode.A_OPT_INACT_IMP_PROF_UNI: (.0, .6, .1),
        ZaeffererProblemMode.B_OPT_INACT_IMP_UNPR_UNI: (.1, .6, .1),
        ZaeffererProblemMode.C_OPT_ACT_IMP_PROF_BI: (.0, .4, .7),
        ZaeffererProblemMode.D_OPT_ACT_IMP_UNPR_BI: (.1, .4, .9),
        ZaeffererProblemMode.E_OPT_DIS_IMP_UNPR_BI: (.1, .4, .7),
    }

    def __init__(self, b=.1, c=.4, d=.7):
        self.b = b
        self.c = c
        self.d = d

        des_vars = [Real(bounds=(0, 1)), Real(bounds=(0, 1))]
        super().__init__(des_vars, n_obj=1)

    def _get_n_valid_discrete(self) -> int:
        return 1

    def _arch_evaluate(self, x: np.ndarray, is_active_out: np.ndarray, f_out: np.ndarray, g_out: np.ndarray,
                       h_out: np.ndarray, *args, **kwargs):
        self._correct_x_impute(x, is_active_out)
        f1 = (x[:, 0] - self.d)**2
        f2 = (x[:, 1] - .5)**2 + self.b
        f2[x[:, 0] <= self.c] = 0.
        f_out[:, 0] = f1+f2

    def _correct_x(self, x: np.ndarray, is_active: np.ndarray):
        is_active[:, 1] = x[:, 0] > self.c  # x2 is active if x1 > c

    @classmethod
    def from_mode(cls, problem_mode: ZaeffererProblemMode):
        b, c, d = cls._mode_map[problem_mode]
        return cls(b=b, c=c, d=d)

    def plot(self, show=True):
        import matplotlib.pyplot as plt

        xx, yy = np.meshgrid(np.linspace(0, 1, 100), np.linspace(0, 1, 100))
        zz = self.evaluate(np.column_stack([xx.ravel(), yy.ravel()])).reshape(xx.shape)

        plt.figure(), plt.title(f'b = {self.b:.1f}, c = {self.c:.1f}, d = {self.d:.1f}')
        plt.colorbar(plt.contourf(xx, yy, zz, 50, cmap='viridis')).set_label('$f$')
        plt.contour(xx, yy, zz, 5, colors='k')
        plt.xlabel('$x_1$'), plt.ylabel('$x_2$')

        if show:
            plt.show()

    def __repr__(self):
        return f'{self.__class__.__name__}(b={self.b}, c={self.c}, d={self.d})'


@deprecated(reason='Not realistic (see docstring)')
class HierarchicalMetaProblemBase(HierarchyProblemBase):
    """
    Meta problem used for increasing the amount of design variables of an underlying mixed-integer/hierarchical problem.
    The idea is that design variables are repeated, and extra design variables are added for switching between the
    repeated design variables. Objectives are then slightly modified based on the switching variable.

    For correct modification of the objectives, a range of the to-be-expected objective function values at the Pareto
    front for each objective dimension should be provided (f_par_range).

    Note that each map will correspond to a new part of the Pareto front.

    DEPRECATED: this class and derived problems should not be used anymore, as they don't represent realistic
    hierarchical problem behavior:
    - One or more design variables might have options that are never selected
    - The spread between option occurrence of design variables is not realistic
    """

    def __init__(self, problem: ArchOptTestProblemBase, n_rep=2, n_maps=4, f_par_range=None):
        self._problem = problem

        # Create design vector: 1 selection variables and n_rep repetitions of underlying design variables
        des_vars = [Choice(options=list(range(n_maps)))]
        for i in range(n_rep):
            des_vars += problem.des_vars

        super().__init__(des_vars, n_obj=problem.n_obj, n_ieq_constr=problem.n_ieq_constr)

        self.n_maps = n_maps
        self.n_rep = n_rep

        # Create the mappings between repeated design variables and underlying: select_map specifies which of the
        # repeated variables to use to replace the values of the original design variables
        # The mappings are semi-random: different for different problem configurations, but repeatable for same configs
        rng = np.random.RandomState(problem.n_var * problem.n_obj * n_rep * n_maps)
        self.select_map = [rng.randint(0, n_rep, (problem.n_var,)) for _ in range(n_maps)]

        # Determine how to move the existing Pareto fronts: move them along the Pareto front dimensions to create a
        # composed Pareto front
        if f_par_range is None:
            f_par_range = 1.
        f_par_range = np.atleast_1d(f_par_range)
        if len(f_par_range) == 1:
            f_par_range = np.array([f_par_range[0]]*problem.n_obj)
        self.f_par_range = f_par_range

        ref_dirs = get_reference_directions("uniform", problem.n_obj, n_partitions=n_maps-1)
        i_rd = np.linspace(0, ref_dirs.shape[0]-1, n_maps).astype(int)
        self.f_mod = (ref_dirs[i_rd, :]-.5)*f_par_range

    def _get_n_valid_discrete(self) -> int:
        return self._problem.get_n_valid_discrete()*self.n_maps

    def _arch_evaluate(self, x: np.ndarray, is_active_out: np.ndarray, f_out: np.ndarray, g_out: np.ndarray,
                       h_out: np.ndarray, *args, **kwargs):
        self._correct_x_impute(x, is_active_out)

        xp, _ = self._get_xp_idx(x)
        f_mod = np.empty((x.shape[0], self.n_obj))
        for i in range(x.shape[0]):
            f_mod[i, :] = self.f_mod[int(x[i, 0]), :]

        fp, g = self._problem.evaluate(xp, return_values_of=['F', 'G'])
        f_out[:, :] = fp+f_mod
        if self.n_ieq_constr > 0:
            g_out[:, :] = g

    def _correct_x(self, x: np.ndarray, is_active: np.ndarray):
        is_active[:, 1:] = False

        xp, i_x_u = self._get_xp_idx(x)
        _, is_active_u = self._problem.correct_x(xp)
        for i in range(x.shape[0]):
            is_active[i, i_x_u[i, :]] = is_active_u[i, :]

    def _get_xp_idx(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Select design variables of the underlying problem based on the repeated variables and the selected mapping"""
        xp = np.empty((x.shape[0], self._problem.n_var))
        i_x_u = np.empty((x.shape[0], self._problem.n_var), dtype=int)
        for i in range(x.shape[0]):
            idx = int(x[i, 0])
            select_map = self.select_map[idx]
            i_x_u[i, :] = i_x_underlying = 1+select_map*len(select_map)+np.arange(0, len(select_map))
            xp[i, :] = x[i, i_x_underlying]

        return xp, i_x_u

    def run_test(self, show=True):
        from pymoo.optimize import minimize
        from pymoo.algorithms.moo.nsga2 import NSGA2

        print(f'Running hierarchical metaproblem: {self.n_var} vars ({self.n_rep} rep, {self.n_maps} maps), '
              f'{self.n_obj} obj, {self.n_ieq_constr} constr')
        res = minimize(self, NSGA2(pop_size=200), termination=('n_gen', 200))

        idx_rep = res.X[:, 0]
        xp, _ = self._get_xp_idx(res.X)
        w_idx = xp[:, 11]*2 + xp[:, 12]
        sp_idx = idx_rep * self.n_rep + w_idx
        sp_labels = ['Rep. %d, SP %d' % (i_rep+1, i+1) for i_rep in range(self.n_rep) for i in range(4)]

        self.plot_sub_problems(sp_idx, res.F, sp_labels=sp_labels, show=show)

    @staticmethod
    def plot_sub_problems(sp_idx: np.ndarray, f: np.ndarray, sp_labels=None, show=True):
        import matplotlib.pyplot as plt

        if f.shape[1] != 2:
            raise RuntimeError('Only for bi-objective optimization!')

        plt.figure(figsize=(4, 2))
        colors = plt.get_cmap('tab10')
        for sp_val in np.unique(sp_idx):
            sp_val = int(sp_val)
            sp_idx_mask = sp_idx == sp_val
            label = ('SP %d' % (sp_val+1,)) if sp_labels is None else sp_labels[sp_val]
            plt.scatter(f[sp_idx_mask, 0], f[sp_idx_mask, 1], color=colors.colors[sp_val], s=10, label=label)

        ax = plt.gca()
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        plt.legend(frameon=False)
        plt.xlabel('$f_1$'), plt.ylabel('$f_2$')

        if show:
            plt.show()

    def __repr__(self):
        return f'{self.__class__.__name__}({self._problem}, n_rep={self.n_rep}, n_maps={self.n_maps}, ' \
               f'f_par_range={self.f_par_range})'


@deprecated(reason='Not realistic (see HierarchicalMetaProblemBase docstring)')
class MOHierarchicalTestProblem(HierarchicalMetaProblemBase):
    """
    Multi-objective hierarchical test problem based on the hierarchical rosenbrock problem. Increased number of design
    variables and increased sparseness (approx. 42% of design variables are active in a DOE).

    This is the analytical test problem used in:
    J.H. Bussemaker et al. "Effectiveness of Surrogate-Based Optimization Algorithms for System Architecture
    Optimization." AIAA AVIATION 2021 FORUM. 2021. DOI: 10.2514/6.2021-3095
    """

    def __init__(self):
        super().__init__(MOHierarchicalRosenbrock(), n_rep=2, n_maps=2, f_par_range=[100, 100])

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class Jenatton(HierarchyProblemBase):
    """
    Jenatton test function:
    - https://github.com/facebook/Ax/blob/main/ax/benchmark/problems/synthetic/hss/jenatton.py
    - https://github.com/facebook/Ax/blob/main/ax/metrics/jenatton.py
    """

    def __init__(self):
        des_vars = [
            Choice(options=[0, 1]),  # x1
            Choice(options=[0, 1]),  # x2
            Choice(options=[0, 1]),  # x3
            Real(bounds=(0, 1)),  # x4
            Real(bounds=(0, 1)),  # x5
            Real(bounds=(0, 1)),  # x6
            Real(bounds=(0, 1)),  # x7
            Real(bounds=(0, 1)),  # r8
            Real(bounds=(0, 1)),  # r9
        ]
        super().__init__(des_vars)

    def _get_n_valid_discrete(self) -> int:
        return 4

    def _arch_evaluate(self, x: np.ndarray, is_active_out: np.ndarray, f_out: np.ndarray, g_out: np.ndarray,
                       h_out: np.ndarray, *args, **kwargs):
        for i, xi in enumerate(x):
            if xi[0] == 0:
                if xi[1] == 0:
                    f_out[i, 0] = xi[3]**2 + .1 + xi[7]  # x4^2 + .1 + r8
                else:
                    f_out[i, 0] = xi[4]**2 + .1 + xi[7]  # x5^2 + .1 + r8
            else:
                if xi[2] == 0:
                    f_out[i, 0] = xi[5]**2 + .1 + xi[8]  # x6^2 + .1 + r9
                else:
                    f_out[i, 0] = xi[6]**2 + .1 + xi[8]  # x7^2 + .1 + r9

    def _correct_x(self, x: np.ndarray, is_active: np.ndarray):
        for i in [2, 5, 6, 8]:  # x1 = 0: x3, x6, x7, r9 inactive
            is_active[x[:, 0] == 0, i] = False
        is_active[(x[:, 0] == 0) & (x[:, 1] == 0), 4] = False  # x2 = 0: x5 inactive
        is_active[(x[:, 0] == 0) & (x[:, 1] == 1), 3] = False  # x2 = 1: x4 inactive

        for i in [1, 4, 5, 7]:  # x2, x4, x5, r8 inactive
            is_active[x[:, 0] == 1, i] = False
        is_active[(x[:, 0] == 1) & (x[:, 2] == 0), 6] = False  # x3 = 0: x7 inactive
        is_active[(x[:, 0] == 1) & (x[:, 2] == 1), 5] = False  # x3 = 1: x6 inactive


class TunableHierarchicalMetaProblem(HierarchyProblemBase):
    """
    Meta problem that turns any problem into a realistically-behaving hierarchical optimization problem with directly
    tunable properties: imputation ratio, nr of subproblems, options per discrete variable, ratio between continuous and
    discrete variables. Note that these properties assume a non-hierarchical underlying problem.

    It does this by:
    - Determining the best nr of design variables and options per design variable to get the requested nr of subproblems
    - Creating all design vectors using the Cartesian product
    - Removing design vectors until the desired nr of subproblems is achieved, without increasing imp ratio too much
    - Splitting design variables until the desired imputation ratio is achieved
    - Initialize the underlying test problem with enough continuous vars to satisfy the continuous-to-discrete ratio
    - Define how each subproblem modifies the underlying problem's objectives and constraints
    """

    def __init__(self, problem_factory: Callable[[int], ArchOptTestProblemBase], imp_ratio: float, n_subproblem: int,
                 n_opts=3, cont_ratio=1., repr_str=None):
        self._repr_str = repr_str

        # Create design vectors by Cartesian product to be as close to the nr of requested subproblems as possible
        n_opt_uniform = np.ones((int(np.ceil(np.log(n_subproblem)/np.log(n_opts))),), dtype=int)*n_opts
        n_opt_variants = [n_opt_uniform]
        if len(n_opt_uniform) > 1:
            n_opt_variants.append(np.array(list(n_opt_uniform[:-1])+[n_opts+1]))
            n_opt_variants.append(np.array(list(n_opt_uniform[:-2])+[n_opts+1]))
        if n_opts > 2:
            for n_full in range(len(n_opt_uniform)):
                n_remaining = n_subproblem/n_opts**n_full
                n_one_less = np.ceil(np.log(n_remaining)/np.log(n_opts-1))
                n_opt_variants.append(np.array([n_opts]*n_full + [n_opts-1]*int(n_one_less)))

        n_declared = np.array([np.prod(n) for n in n_opt_variants])
        i_variant = np.where(n_declared >= n_subproblem)[0]
        i_variant = i_variant[np.argmin(n_declared[i_variant])]
        n_dv_opts = n_opt_variants[i_variant]

        x_discrete = np.array(list(itertools.product(*[list(range(n)) for n in n_dv_opts])))
        is_act_discrete = np.ones(x_discrete.shape, dtype=bool)

        # Eliminate options until we reach the desired number of subproblems
        def _imp_ratio(x_discrete_):
            return np.prod(np.max(x_discrete_, axis=0)+1)/x_discrete_.shape[0]

        assert _imp_ratio(x_discrete) == 1.
        while x_discrete.shape[0] > n_subproblem:
            n_remove = x_discrete.shape[0]-n_subproblem
            n_remain_min = None
            remove_mask = None

            last_init_value = sorted(list(set(x_discrete[:, 0])))[-1]
            last_init_value_mask = x_discrete[:, 0] == last_init_value
            ix_last_init_value = np.where(last_init_value_mask)[0]
            x_discrete_last = x_discrete[ix_last_init_value, :]

            for ix_check in itertools.product(*([[True]]+[[False, True] for _ in range(x_discrete.shape[1]-1)])):
                ix_check = np.array(ix_check)
                dv_unique, idx = np.unique(x_discrete_last[:, ix_check], axis=0, return_inverse=True)
                dv_sub_last_mask = idx == (len(dv_unique)-1)
                n_remain = n_remove-np.sum(dv_sub_last_mask)
                if n_remain < 0:
                    continue
                if n_remain_min is None or n_remain < n_remain_min:
                    n_remain_min = n_remain
                    ix_check_i = np.where(ix_check)[0]
                    remove_mask = dv_sub_last_mask, ix_check_i

            if n_remain_min is None:
                break

            # Remove the specific design vectors if thereby we do not violate the imputation ratio constraint
            init_sub_mask, ix_check_i = remove_mask
            mask = last_init_value_mask
            mask[last_init_value_mask] = init_sub_mask
            inv_mask = np.where(~mask)[0]

            x_removed = x_discrete[mask, :]
            x_discrete_filtered = x_discrete[inv_mask, :]
            if _imp_ratio(x_discrete_filtered) > imp_ratio:
                break
            x_discrete = x_discrete_filtered
            is_act_discrete = is_act_discrete[inv_mask, :]

            # Set is_active flags
            ix_filter, ix_options_check = ix_check_i[:-1], ix_check_i[-1]
            if len(ix_filter) > 0:
                remains_mask = np.all(x_discrete_filtered[:, ix_filter] == x_removed[:, ix_filter][0, :], axis=1)
                if np.max(x_discrete_filtered[remains_mask, ix_options_check]) == 0:
                    is_act_discrete[remains_mask, ix_options_check] = False

        # Separate design variables until we meet the imputation ratio requirement
        current_sep_mask = np.arange(x_discrete.shape[0])
        ix_started = [set() for _ in range(x_discrete.shape[1])]
        nothing_found_flag = False
        while _imp_ratio(x_discrete) < imp_ratio:
            ix_chain = []
            for i_dv in range(x_discrete.shape[1]):
                if np.any(~is_act_discrete[current_sep_mask, i_dv]):
                    continue
                x_discrete_i = x_discrete[current_sep_mask, i_dv]
                x_unique = np.where(np.bincount(x_discrete_i) > 0)[0]
                i_value_sel = [tuple(ix_chain+[ix]) for ix in range(len(x_unique))]
                i_value_sel = [iv for iv in i_value_sel if iv not in ix_started[i_dv]]
                if len(i_value_sel) > 1:
                    next_sep_mask = current_sep_mask[x_discrete_i == i_value_sel[0][-1]]
                    if len(next_sep_mask) > 1:
                        ix_started[i_dv].add(i_value_sel[0])
                        break
                ix_chain.append(x_unique[0])
            else:
                if nothing_found_flag:
                    break
                current_sep_mask = np.arange(x_discrete.shape[0])
                nothing_found_flag = True
                continue
            nothing_found_flag = False

            # Determine which variable to separate
            for i_sep in reversed(list(range(1, x_discrete.shape[1]))):
                if np.any(~is_act_discrete[next_sep_mask, i_sep]):
                    continue
                break
            else:
                break

            # Separate the selected design variable into a new variable at the end of the vector
            x_discrete_sep = np.zeros((x_discrete.shape[0], x_discrete.shape[1]+1), dtype=int)
            x_discrete_sep[:, :-1] = x_discrete.copy()
            x_discrete_sep[next_sep_mask, i_sep:] = 0
            x_discrete_sep[next_sep_mask, -1] = x_discrete[next_sep_mask, i_sep]

            is_act_sep = np.column_stack([is_act_discrete, np.zeros((x_discrete.shape[0],), dtype=bool)])
            is_act_sep[next_sep_mask, i_sep:] = False
            is_act_sep[next_sep_mask, -1] = is_act_discrete[next_sep_mask, i_sep]

            # Check imputation ratio constraint
            if _imp_ratio(x_discrete_sep) > imp_ratio:
                break
            x_discrete = x_discrete_sep
            is_act_discrete = is_act_sep
            current_sep_mask = next_sep_mask
            ix_started.append(set())

        self._x_sub = x_discrete
        self._is_act_sub = is_act_discrete

        # Initialize underlying problem
        self._n_cont = n_cont = max(0, int(x_discrete.shape[1]*cont_ratio))
        self._problem = problem = problem_factory(max(2, n_cont))
        pf: np.ndarray = problem.pareto_front()
        pf_min, pf_max = np.min(pf, axis=0), np.max(pf, axis=0)
        is_same = np.abs(pf_max-pf_min) < 1e-10
        pf_max[is_same] = pf_min[is_same]+1.
        self._pf_min, self._pf_max = pf_min, pf_max

        # Define subproblem transformations
        n_sub = x_discrete.shape[0]
        self._transform = transform = np.zeros((n_sub, problem.n_obj*2))
        n_trans = transform.shape[1]
        n_cycles = np.arange(n_trans)+1
        offset = .25*np.linspace(1, 0, n_trans+1)[:n_trans]
        for i_trans in range(n_trans):
            func = np.sin if i_trans % 2 == 0 else np.cos
            transform[:, i_trans] = func((np.linspace(0, 1, n_sub+1)[:n_sub]+offset[i_trans])*2*np.pi*n_cycles[i_trans])

        mutual_distance = distance.cdist(transform, transform, metric='cityblock')
        np.fill_diagonal(mutual_distance, np.nan)
        # if np.any(mutual_distance < 1e-10):
        #     raise RuntimeError('Duplicate transformations!')

        # Define design variables
        des_vars = []
        for dv_opts in (np.max(x_discrete, axis=0)+1):
            des_vars.append(Choice(options=list(range(int(dv_opts)))))

        for i_dv, des_var in enumerate(problem.des_vars[:n_cont]):
            if isinstance(des_var, Real):
                des_vars.append(Real(bounds=des_var.bounds))
            elif isinstance(des_var, Integer):
                des_vars.append(Integer(bounds=des_var.bounds))
            elif isinstance(des_var, Choice):
                des_vars.append(Choice(options=des_var.options))
            else:
                raise RuntimeError(f'Design variable type not supported: {des_var!r}')

        super().__init__(des_vars, n_obj=problem.n_obj, n_ieq_constr=problem.n_ieq_constr,
                         n_eq_constr=problem.n_eq_constr)

        self.__correct_output = {}

    def _get_n_valid_discrete(self) -> int:
        n_discrete_underlying = self._problem.get_n_valid_discrete()
        return n_discrete_underlying*self._x_sub.shape[0]

    def _gen_all_discrete_x(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        x_sub, is_act_sub = self._x_sub, self._is_act_sub
        if self._n_cont == 0:
            return x_sub, is_act_sub

        x_problem, is_act_problem = HierarchicalExhaustiveSampling().get_all_x_discrete(self._problem)

        n_sub_select = x_sub.shape[0]
        x_sub = np.repeat(x_sub, x_problem.shape[0], axis=0)
        is_act_sub = np.repeat(is_act_sub, x_problem.shape[0], axis=0)
        x_problem = np.tile(x_problem, (n_sub_select, 1))
        is_act_problem = np.tile(is_act_problem, (n_sub_select, 1))

        x_all = np.column_stack([x_sub, x_problem])
        is_act_all = np.column_stack([is_act_sub, is_act_problem])
        return x_all, is_act_all

    def _arch_evaluate(self, x: np.ndarray, is_active_out: np.ndarray, f_out: np.ndarray, g_out: np.ndarray,
                       h_out: np.ndarray, *args, **kwargs):
        # Correct and impute
        self._correct_x_impute(x, is_active_out)
        i_sub_selected = self.__correct_output['i_sub_sel']
        n_sub = self._x_sub.shape[1]

        # Evaluate underlying problem
        x_underlying = self._get_x_underlying(x[:, n_sub:])
        out = self._problem.evaluate(x_underlying, return_as_dictionary=True)
        if 'G' in out:
            g_out[:, :] = out['G']
        if 'H' in out:
            h_out[:, :] = out['H']

        # Transform outputs
        f_out[:, :] = self._transform_out(out['F'], i_sub_selected)

    def _transform_out(self, f: np.ndarray, i_sub_selected: np.ndarray) -> np.ndarray:
        pf_min, pf_max = self._pf_min, self._pf_max
        trans = self._transform
        f_norm = (f-pf_min)/(pf_max-pf_min)
        for i_obj in range(f.shape[1]):
            f_other = f_norm.copy()
            f_other[:, i_obj] = 0

            translate_shear = trans[i_sub_selected, i_obj::f.shape[1]]
            translate, scale = translate_shear.T
            fi_norm = f_norm[:, i_obj]
            fi_norm += .2*translate
            fi_norm = (fi_norm-.5)*(.5+.4*scale)+.5
            f_norm[:, i_obj] = fi_norm

        return f_norm*(pf_max-pf_min) + pf_min

    def _correct_x(self, x: np.ndarray, is_active: np.ndarray):
        # Match sub-problem selection design variables
        x_sub, is_act_sub = self._x_sub, self._is_act_sub
        n_sub = x_sub.shape[1]
        x_dist = distance.cdist(x[:, :n_sub], x_sub, metric='cityblock')
        i_sub_selected = np.zeros((x.shape[0],), dtype=int)
        for i in range(x.shape[0]):
            # Get minimum distance
            i_min_dist = np.argmin(x_dist[i, :])
            i_sub_selected[i] = i_min_dist

            # Impute if the design vector didn't match exactly
            if x_dist[i, i_min_dist] > 0:
                x[i, :n_sub] = x_sub[i_min_dist, :]
                is_active[i, :n_sub] = is_act_sub[i_min_dist, :]

        # Correct design vectors of underlying problem
        n_cont = self._n_cont
        x_underlying = self._get_x_underlying(x[:, n_sub:])
        x_problem, is_act_problem = self._problem.correct_x(x_underlying)
        x[:, n_sub:] = x_problem[:, :n_cont]
        is_active[:, n_sub:] = is_act_problem[:, :n_cont]

        self.__correct_output = {'i_sub_sel': i_sub_selected}

    def _get_x_underlying(self, x_underlying):
        if self._n_cont == 0:
            return np.ones((x_underlying.shape[0], self._problem.n_var))*.5*(self._problem.xl+self._problem.xu)
        return x_underlying

    def plot_i_sub_problem(self, x: np.ndarray = None, show=True):
        import matplotlib.pyplot as plt
        if x is None:
            x = self.pareto_set()
        x, _ = self.correct_x(x)
        f = self.evaluate(x, return_as_dictionary=True)['F']
        i_sub_selected = self.__correct_output['i_sub_sel']

        plt.figure()
        f0 = f[:, 0]
        f1 = f[:, 1] if f.shape[1] > 1 else f0
        for i_sp in np.unique(i_sub_selected):
            mask = i_sub_selected == i_sp
            plt.scatter(f0[mask], f1[mask], s=10, marker='o', label=f'#{i_sp+1}')
        plt.legend(loc='upper left', bbox_to_anchor=(1, 1), frameon=False)
        plt.tight_layout()
        if show:
            plt.show()

    def plot_transformation(self, show=True):
        import matplotlib.pyplot as plt
        plt.figure()
        if1 = 0 if self._problem.n_obj < 2 else 1

        pf = self._problem.pareto_front()
        plt.scatter(pf[:, 0], pf[:, if1], s=10, marker='o', label='Orig')

        for i_sub in range(self._x_sub.shape[0]):
            pf_transformed = self._transform_out(pf, np.ones((pf.shape[0],), dtype=int)*i_sub)
            plt.scatter(pf_transformed[:, 0], pf_transformed[:, if1], s=10, marker='o', label=f'#{i_sub+1}')

        plt.legend(loc='upper left', bbox_to_anchor=(1, 1), frameon=False)
        plt.tight_layout()
        if show:
            plt.show()

    def __repr__(self):
        if self._repr_str is not None:
            return self._repr_str
        return f'{self.__class__.__name__}()'


class HierBranin(TunableHierarchicalMetaProblem):

    def __init__(self):
        factory = lambda n: MDBranin()
        super().__init__(factory, imp_ratio=5., n_subproblem=50, n_opts=3)


class TunableZDT1(TunableHierarchicalMetaProblem):

    def __init__(self, imp_ratio=1., n_subproblem=100, n_opts=3, cont_ratio=1.):
        factory = lambda n: NoHierarchyWrappedProblem(ZDT1(n_var=n))
        super().__init__(factory, imp_ratio=imp_ratio, n_subproblem=n_subproblem, n_opts=n_opts, cont_ratio=cont_ratio)


class HierZDT1Small(TunableZDT1):

    def __init__(self):
        super().__init__(imp_ratio=2., n_subproblem=10, n_opts=3, cont_ratio=1)


class HierZDT1(TunableZDT1):

    def __init__(self):
        super().__init__(imp_ratio=5., n_subproblem=200, n_opts=3, cont_ratio=.5)


class HierZDT1Large(TunableZDT1):

    def __init__(self):
        super().__init__(imp_ratio=20., n_subproblem=2000, n_opts=4, cont_ratio=1.)


class HierDiscreteZDT1(TunableZDT1):

    def __init__(self):
        super().__init__(imp_ratio=5., n_subproblem=2000, n_opts=4, cont_ratio=0)


if __name__ == '__main__':
    # HierarchicalGoldstein().print_stats()
    # MOHierarchicalGoldstein().print_stats()
    # # HierarchicalGoldstein().plot_pf()
    # MOHierarchicalGoldstein().plot_pf()

    # HierarchicalRosenbrock().print_stats()
    # MOHierarchicalRosenbrock().print_stats()
    # # HierarchicalRosenbrock().plot_pf()
    # MOHierarchicalRosenbrock().plot_pf()

    # ZaeffererHierarchical.from_mode(ZaeffererProblemMode.A_OPT_INACT_IMP_PROF_UNI).print_stats()
    # ZaeffererHierarchical.from_mode(ZaeffererProblemMode.A_OPT_INACT_IMP_PROF_UNI).plot_pf()
    # ZaeffererHierarchical.from_mode(ZaeffererProblemMode.A_OPT_INACT_IMP_PROF_UNI).plot_design_space()

    # MOHierarchicalTestProblem().print_stats()
    # MOHierarchicalTestProblem().plot_pf()

    # Jenatton().print_stats()
    # # Jenatton().plot_pf()

    # p = HierBranin()
    p = HierZDT1Small()
    # p = HierZDT1()
    # p = HierZDT1Large()
    # p = HierDiscreteZDT1()
    p.print_stats()
    # p.reset_pf_cache()
    # p.plot_pf()
    # p.plot_transformation(show=False)
    # p.plot_i_sub_problem()
