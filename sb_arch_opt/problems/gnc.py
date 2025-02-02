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

This test suite contains the discrete, hierarchical, multi-objective Guidance, Navigation & Control test problem.
"""
import itertools
import numpy as np
from typing import List
from pymoo.core.variable import Integer, Choice
from sb_arch_opt.problems.hierarchical import HierarchyProblemBase

__all__ = ['GNCProblemBase', 'GNCNoActNrType', 'GNCNoActType', 'GNCNoActNr', 'GNCNoAct',
           'GNCNoNrType', 'GNCNoType', 'GNCNoNr', 'GNC']


class GNCProblemBase(HierarchyProblemBase):
    """
    Guidance, Navigation and Control architecture design problem, from chapter 15 of:
    Crawley et al., "System Architecture - Strategy and Product Development for Complex Systems", 2015.

    The challenge is to find the most optimal selection and connection patterns from Sensors to Computers,
    and Computers to Actuators. The number and type of each element can be selected. The architecture is evaluated in
    terms of reliability (more connections and more reliable components lead to more system-level reliability) and
    mass (more reliable components are heavier). This is therefore a multi-objective optimization problem.

    Component mass and probabilities are taken from:
    Apaza & Selva, "Automatic Composition of Encoding Scheme and Search Operators
    in System Architecture Optimization", 2021.
    """
    _force_get_discrete_rates = False

    mass = {
        'S': {'A': 3., 'B': 6., 'C': 9.},
        'C': {'A': 3., 'B': 5., 'C': 10.},
        'A': {'A': 3.5, 'B': 5.5, 'C': 9.5},
    }
    failure_rate = {
        'S': {'A': .00015, 'B': .0001, 'C': .00005},
        'C': {'A': .0001, 'B': .00004, 'C': .00002},
        'A': {'A': .00008, 'B': .0002, 'C': .0001},
    }

    def __init__(self, choose_nr=True, n_max=3, choose_type=True, actuators=True):
        self.choose_nr = choose_nr
        self.n_max = n_max
        self.choose_type = choose_type
        self.actuators = actuators

        # If nr and types are not chosen, there is no way to vary system mass
        n_obj = 2 if self.choose_nr or self.choose_type else 1

        des_vars = self._get_des_vars()
        super().__init__(des_vars, n_obj=n_obj)

    def _get_n_valid_discrete(self) -> int:
        # Pre-count the number of possible connections, taking into account that each connector at least needs one
        # We can ignore any combinations where there are either 1 sources or targets, as there there is only 1
        # connection possibility (namely all-to-one or one-to-all)
        def _iter_conns(n_src_, n_tgt_):
            # Loop over the number of outgoing connections for the current source node (at least one)
            for n_conn_src in range(1, n_tgt_+1):
                # Loop over the combinations of target node selections
                for i_conn_targets in itertools.combinations(list(range(n_tgt_)), n_conn_src):
                    # Prepare connection matrix of size (n_src x n_tgt), where 1 denotes a made connection
                    src_conn_matrix = np.zeros((n_src_, n_tgt_), dtype=int)
                    src_conn_matrix[0, list(i_conn_targets)] = 1

                    # If we only have 1 source node left, this is the final matrix
                    if n_src_ == 1:
                        yield src_conn_matrix
                        continue

                    # Otherwise, loop over possible connection matrices by the remaining source nodes
                    for next_src_conn_matrix in _iter_conns(n_src_-1, n_tgt_):
                        conn_matrix_ = src_conn_matrix.copy()
                        conn_matrix_[1:, :] = next_src_conn_matrix
                        yield conn_matrix_

        n_comb_conn = {}
        for n_src, n_tgt in itertools.product(list(range(2, self.n_max+1)), list(range(2, self.n_max+1))):

            # Loop over connection matrices
            n_combinations = 0
            for conn_matrix in _iter_conns(n_src, n_tgt):
                # Check if all nodes have at least one connection
                if np.any(np.sum(conn_matrix, axis=0) == 0) or np.any(np.sum(conn_matrix, axis=1) == 0):
                    continue
                n_combinations += 1

            n_comb_conn[n_src, n_tgt] = n_comb_conn[n_tgt, n_src] = n_combinations

        # Loop over the number of object instances
        n_node_exist = list(range(1, self.n_max+1)) if self.choose_nr else [self.n_max]
        n_actuators = n_node_exist if self.actuators else [0]
        n_valid = 0
        for n_objs in itertools.product(n_node_exist, n_node_exist, n_actuators):
            # Count the number of possible type selections
            n_inst_comb = 1
            if self.choose_type:
                for n in n_objs:
                    if n > 0:
                        n_inst_comb *= len(list(itertools.combinations_with_replacement('ABC', n)))

            # Count the number of possible inter-object connections
            for n_src, n_tgt in zip(n_objs[:-1], n_objs[1:]):
                # If there are no targets (actuators) to connect to, or there is only 1 of either type skip as there are
                # no additional combinations possible
                if n_tgt == 0:
                    continue
                if n_src == 1 or n_tgt == 1:
                    continue

                n_inst_comb *= n_comb_conn[n_src, n_tgt]

            n_valid += n_inst_comb
        return n_valid

    def _get_des_vars(self):
        des_vars = []

        # Choose the nr of sensors, computers, [actuators]
        # We simply define one integer design variable per object type to select the nr of instances
        n_obj_types = 3 if self.actuators else 2
        if self.choose_nr:
            for _ in range(n_obj_types):
                des_vars.append(Integer(bounds=(1, self.n_max)))

        # Choose the type of the objects (A, B, or C)
        # Here the thing is that we should select types without including permutations of these selections, otherwise
        # the opportunity arises of defining duplicate (in terms of performance) architectures:
        # [A] --> [B]     is equivalent to     [B] -\/-> [B]       and         [B] --> [C]
        # [B] --> [C]                          [A] -/\-> [C]                   [A] --> [B]
        # therefore, the type selection choices should only represent unordered combinations:
        # AAA, AAB, AAC, ABB, ABC, ACC, BBB, BBC, BCC, CCC
        # The best way to represent this is by having one categorical design variable per object instance and then
        # correcting the design variable values to only represent unordered combinations
        if self.choose_type:
            for _ in range(n_obj_types):
                des_vars += [Choice(options=['A', 'B', 'C']) for _ in range(self.n_max)]

        # Choose the connections among objects
        # Here we assign each possible connection edge to one categorical design variable (yes/no), representing whether
        # the connection is established or not; the constraint that each object should have at least one connection is
        # enforced by repair/imputation
        for _ in range(n_obj_types-1):
            des_vars += [Choice(options=[False, True]) for _ in range(self.n_max*self.n_max)]

        return des_vars

    def _is_conditionally_active(self) -> List[bool]:
        # If we do not choose the number of objects, all variables are always active
        if not self.choose_nr:
            return [False]*self.n_var

        is_cond_act = [True]*self.n_var
        n_obj_types = 3 if self.actuators else 2
        i_dv = 0
        for _ in range(n_obj_types):
            # Choose nr of obj is always active
            is_cond_act[i_dv] = False
            i_dv += 1

        if self.choose_type:
            for _ in range(n_obj_types):
                for i in range(self.n_max):
                    # Choose type is active is not choose nr OR for the first instance of each object type
                    if i == 0:
                        is_cond_act[i_dv] = False
                        i_dv += 1

        for _ in range(n_obj_types-1):
            for i in range(self.n_max):
                for j in range(self.n_max):
                    # Connections between the first object instances are always active
                    if i == 0 and j == 0:
                        is_cond_act[i_dv] = False
                    i_dv += 1

        return is_cond_act

    def _correct_x(self, x: np.ndarray, is_active: np.ndarray):
        n_obj_types = 3 if self.actuators else 2
        n_x_conn = self.n_max*self.n_max
        for i, x_i in enumerate(x):
            is_active_i = is_active[i, :]
            j = 0

            # Get the number of instantiated objects
            if self.choose_nr:
                n_inst = x_i[j:j+n_obj_types].astype(int)
                j += n_obj_types
            else:
                n_inst = np.ones((n_obj_types,), dtype=int)*self.n_max

            # Correct the object types
            if self.choose_type:
                for n_obj in n_inst:
                    x_obj_type = x_i[j:j+self.n_max]

                    # Set type selections for non-instantiated objects to inactive
                    is_active_i[j+n_obj:j+self.n_max] = False

                    # Correct types for instantiated objects to only select unordered combinations: subsequent variables
                    # cannot have a lower value than prior ones
                    last_type_sel = x_obj_type[0]
                    for dj in range(1, n_obj):
                        if x_obj_type[dj] < last_type_sel:
                            x_i[j+dj] = last_type_sel
                        else:
                            last_type_sel = x_obj_type[dj]

                    j += self.n_max

            # Correct the connections
            for i_conn in range(n_obj_types-1):
                x_conn = x_i[j:j+n_x_conn].reshape((self.n_max, self.n_max))
                is_active_conn = is_active_i[j:j+n_x_conn].reshape((self.n_max, self.n_max))

                # Deactivate connections for non-instantiated objects
                n_src, n_tgt = n_inst[i_conn], n_inst[i_conn+1]
                is_active_conn[n_src:, :] = False
                is_active_conn[:, n_tgt:] = False

                # Ensure that each connector has at least one connection
                x_conn_active = x_conn[:n_src, :n_tgt]
                for i_src, n_conn_src in enumerate(np.sum(x_conn_active, axis=1)):
                    if n_conn_src == 0:
                        # Select the same target as the source to make a connection, or the last available
                        i_tgt = min(i_src, n_tgt-1)
                        x_conn_active[i_src, i_tgt] = 1

                for i_tgt, n_conn_tgt in enumerate(np.sum(x_conn_active, axis=0)):
                    if n_conn_tgt == 0:
                        i_src = min(i_tgt, n_src-1)
                        x_conn_active[i_src, i_tgt] = 1

                j += n_x_conn

    def _arch_evaluate(self, x: np.ndarray, is_active_out: np.ndarray, f_out: np.ndarray, g_out: np.ndarray,
                       h_out: np.ndarray, *args, **kwargs):
        # First correct the design variable so that only valid architectures are evaluated
        self._correct_x_impute(x, is_active_out)

        # Get object-type labels
        n_obj_types = 3 if self.actuators else 2
        j = n_obj_types if self.choose_nr else 0
        obj_type_cat_values = [[self.get_categorical_values(x, j+i_obj*self.n_max+dj) for dj in range(self.n_max)]
                               for i_obj in range(n_obj_types)]

        # Loop over architectures
        n_x_conn = self.n_max*self.n_max
        for i, x_i in enumerate(x):
            j = 0

            # Get the number of instantiated objects
            if self.choose_nr:
                n_inst = x_i[j:j+n_obj_types].astype(int)
                j += n_obj_types
            else:
                n_inst = np.ones((n_obj_types,), dtype=int)*self.n_max

            # Get the object types
            obj_types = []
            if self.choose_type:
                for i_obj, n_obj in enumerate(n_inst):
                    obj_types.append([obj_type_cat_values[i_obj][dj][i] for dj in range(n_obj)])
                    j += self.n_max
            else:
                types = ['A', 'B', 'C']
                for n in n_inst:
                    type_cycle = itertools.cycle(types)
                    obj_types.append([next(type_cycle) for _ in range(n)])

            # Get the connections
            conn_edges = []
            for i_conn in range(n_obj_types-1):
                x_conn = x_i[j:j+n_x_conn].reshape((self.n_max, self.n_max)).astype(bool)

                edges = []
                n_src, n_tgt = n_inst[i_conn], n_inst[i_conn+1]
                for i_src in range(n_src):
                    for i_tgt in range(n_tgt):
                        if x_conn[i_src, i_tgt]:
                            edges.append((i_src, i_tgt))

                conn_edges.append(edges)
                j += n_x_conn

            # Calculate metrics
            mass = self._calc_mass(obj_types[0], obj_types[1], actuator_types=obj_types[2] if self.actuators else None)
            failure_rate = self._calc_failure_rate(obj_types[0], obj_types[1], conn_edges[0],
                                                   actuator_types=obj_types[2] if self.actuators else None,
                                                   act_conns=conn_edges[1] if self.actuators else None)

            f_out[i, 0] = failure_rate
            if f_out.shape[1] > 1:
                f_out[i, 1] = mass

    @classmethod
    def _calc_mass(cls, sensor_types, computer_types, actuator_types=None):
        mass = sum([cls.mass['S'][type_] for type_ in sensor_types])
        mass += sum([cls.mass['C'][type_] for type_ in computer_types])
        if actuator_types is not None:
            mass += sum([cls.mass['A'][type_] for type_ in actuator_types])
        return mass

    @classmethod
    def _calc_failure_rate(cls, sensor_types, computer_types, conns, actuator_types=None, act_conns=None):

        # Get item failure rates
        rate = cls.failure_rate
        failure_rates = [np.array([rate['S'][type_] for type_ in sensor_types]),
                         np.array([rate['C'][type_] for type_ in computer_types])]
        obj_conns = [conns]
        if actuator_types is not None:
            failure_rates.append(np.array([rate['A'][type_] for type_ in actuator_types]))
            obj_conns.append(act_conns)

        conn_matrices = []
        for i, edges in enumerate(obj_conns):
            matrix = np.zeros((len(failure_rates[i]), len(failure_rates[i+1])), dtype=int)
            for i_src, i_tgt in edges:
                matrix[i_src, i_tgt] = 1
            conn_matrices.append(matrix)

        # Loop over combinations of failed components
        def _branch_failures(i_rates=0, src_connected_mask=None) -> float:
            calc_downstream = i_rates < len(conn_matrices)-1
            rates, tgt_rates = failure_rates[i_rates], failure_rates[i_rates+1]
            conn_mat = conn_matrices[i_rates]

            # Loop over failure scenarios
            if src_connected_mask is None:
                src_connected_mask = np.ones((len(rates),), dtype=bool)
            total_rate = 0.
            for ok_sources in itertools.product(*[([False, True] if src_connected_mask[i_conn] else [False])
                                                  for i_conn in range(len(rates))]):
                if i_rates > 0 and not any(ok_sources):
                    continue

                # Calculate probability of this scenario occurring
                ok_sources = list(ok_sources)
                occurrence_prob = rates.copy()
                occurrence_prob[ok_sources] = 1-occurrence_prob[ok_sources]
                prob = 1.
                for partial_prob in occurrence_prob[src_connected_mask]:
                    prob *= partial_prob
                occurrence_prob = prob

                # Check which targets are still connected in this scenario
                conn_mat_ok = conn_mat[ok_sources, :].T
                connected_targets = np.zeros((conn_mat_ok.shape[0],), dtype=bool)
                for i_conn_tgt in range(conn_mat_ok.shape[0]):
                    connected_targets[i_conn_tgt] = np.any(conn_mat_ok[i_conn_tgt])

                # If no connected targets are available the system fails
                tgt_failure_rates = tgt_rates[connected_targets]
                if len(tgt_failure_rates) == 0:
                    total_rate += occurrence_prob
                    continue

                # Calculate the probability that the system fails because all remaining connected targets fail
                all_tgt_fail_prob = 1.
                for prob in tgt_failure_rates:
                    all_tgt_fail_prob *= prob
                total_rate += occurrence_prob*all_tgt_fail_prob

                # Calculate the probability that the system fails because remaining downstream connected targets fail
                if calc_downstream:
                    total_rate += occurrence_prob*_branch_failures(
                        i_rates=i_rates+1, src_connected_mask=connected_targets)

            return total_rate

        failure_rate = _branch_failures()
        return np.log10(failure_rate)

    def __repr__(self):
        return f'{self.__class__.__name__}(choose_nr={self.choose_nr}, n_max={self.n_max}, ' \
               f'choose_type={self.choose_type}, actuators={self.actuators})'


class GNCNoActNrType(GNCProblemBase):

    def __init__(self):
        super().__init__(choose_type=False, choose_nr=False, actuators=False)

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class GNCNoActType(GNCProblemBase):

    def __init__(self):
        super().__init__(choose_type=False, actuators=False)

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class GNCNoActNr(GNCProblemBase):

    def __init__(self):
        super().__init__(choose_nr=False, actuators=False)

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class GNCNoAct(GNCProblemBase):

    def __init__(self):
        super().__init__(actuators=False)

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class GNCNoNrType(GNCProblemBase):

    def __init__(self):
        super().__init__(choose_type=False, choose_nr=False)

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class GNCNoType(GNCProblemBase):

    def __init__(self):
        super().__init__(choose_type=False)

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class GNCNoNr(GNCProblemBase):

    def __init__(self):
        super().__init__(choose_nr=False)

    def __repr__(self):
        return f'{self.__class__.__name__}()'


class GNC(GNCProblemBase):

    def __init__(self):
        super().__init__()

    def __repr__(self):
        return f'{self.__class__.__name__}()'


if __name__ == '__main__':
    # GNCProblemBase().print_stats()
    # GNCProblemBase().plot_pf()

    GNCNoActNrType().print_stats()
    GNCNoActType().print_stats()
    GNCNoActNr().print_stats()
    GNCNoAct().print_stats()
    GNCNoNrType().print_stats()
    GNCNoType().print_stats()
    GNCNoNr().print_stats()
    GNC().print_stats()

    # GNCNoAct().plot_pf()
    GNC().plot_pf()
