from retrying import retry
from numba import jit
import numpy as np
import random
import math
from collections import OrderedDict


class OptimalKs(object):
    """Base class for OptimalKs.

    Parameters
    ----------
    edgelist : list, required
        Edgelist (bipartite network) for model selection.

    types : list, required
        Types of each node specifying the type membership.

    init_Ka : int, required
        Initial Ka for successive merging and searching for the optimum.

    init_Kb : int, required
        Initial Ka for successive merging and searching for the optimum.

    i_th :  double, optional
        Threshold for the merging step (as described in the main text).

    n_sweeps : int, optional
        Number of calculations performed on each (Ka, Kb) point.

    is_parallel : bool, optional
        Whether the n_sweeps calculation is forked for parallel processes.

    n_cores : int, optional
        If is_parallel == True, the number of cores that is used.

    """

    def __init__(self,
                 edgelist,
                 types,
                 init_Ka=10,
                 init_Kb=10,
                 i_th=0.1,
                 n_sweeps=5,
                 is_parallel=True,
                 n_cores=2,
                 **kwargs):

        import os
        import numpy as np
        from pathos.multiprocessing import ProcessingPool as Pool
        import math
        import subprocess

        self._os = os
        self._np = np
        self._Pool = Pool
        self._math = math
        self._subprocess = subprocess

        # params for the heuristic
        self.ka = int(init_Ka)
        self.kb = int(init_Kb)
        self.INIT_ka = int(init_Ka)
        self.INIT_kb = int(init_Kb)

        self.ITALIC_I_THRESHOLD = float(i_th)
        self._ITALIC_I_THRESHOLD = self.ITALIC_I_THRESHOLD
        self.MAX_NUM_SWEEPS = int(n_sweeps)
        self.PARALLELIZATION = bool(is_parallel)
        self.NUM_CORES = int(n_cores)

        self.types = types
        self.NUM_NODES_A = 0
        self.NUM_NODES_B = 0
        for _type in types:
            if _type == "1":
                self.NUM_NODES_A += 1
            else:
                self.NUM_NODES_B += 1
        self.NUM_NODES = len(types)

        self.edgelist = edgelist
        self.NUM_EDGES = len(self.edgelist)

        # sanity checks:
        assert self.NUM_NODES == self.NUM_NODES_A + self.NUM_NODES_B

        # for the iterator
        self.confident_desc_len = OrderedDict()
        self.confident_m_e_rs = OrderedDict()
        self.confident_italic_I = OrderedDict()
        self.confident_of_group = OrderedDict()
        self.confident_of_group_info = OrderedDict()

        # for debug/temp variables
        self.debug_str = ""
        self.f_edgelist_ = "edgelist-" + str(random.random()) + ".tmp"
        with open(self.f_edgelist_, "wb") as f:
            for edge in self.edgelist:
                f.write(str(edge[0]) + "\t" + edge[1] + "\n")

        # for output
        # self.membership_path = 'membership.txt'
        # try:
        #     self._os.remove(self.membership_path)
        # except:
        #     pass

        # for MCMC
        try:
            self.f_mcmc = kwargs["f_mcmc"]
        except:
            raise BaseException
        else:
            self.mcmc_steps_ = int(kwargs["mcmc_steps"])
            self.mcmc_await_steps_ = int(kwargs["mcmc_await_steps"])
            self.mcmc_cooling_ = str(kwargs["mcmc_cooling"])
            self.mcmc_cooling_param_1 = str(kwargs["mcmc_cooling_param_1"])
            self.mcmc_cooling_param_2 = str(kwargs["mcmc_cooling_param_2"])
            self.mcmc_epsilon_ = str(kwargs["mcmc_epsilon"])

        pass

    def prepare_engine(self, ka, kb):
        """Output shell commands for graph partitioning calculation.

        Parameters
        ----------
        ka : int, required
            Number of communities for type-a nodes to partition.

        kb : int, required
            Number of communities for type-b nodes to partition.
        """
        # membership_path_ = self.membership_path

        # crit = ka != self.INIT_ka or kb != self.INIT_kb
        # if not crit:  # the first step of the algorithm
        #     print("the first step of the algorithm")
        #     pass
        # else:
        #     try:
        #         self.confident_of_group[(ka, kb)]
        #     except Exception as e:
        #         #print(e)
        #         # in order to make the inference faster, we generate the block membership on our own
        #         n_id = [b_id if idx < self.NUM_NODES_A else b_id - self.ka
        #                 for idx, b_id in enumerate(self.confident_of_group[(self.ka, self.kb)])]
        #         if ka - self.ka < 0 and kb - self.kb >= 0:
        #             _n_id = [_id - 1 if idx < self.NUM_NODES_A and _id == self.ka - 1 else
        #                      _id for idx, _id in enumerate(n_id)]
        #         elif kb - self.kb < 0 and ka - self.ka >= 0:
        #             _n_id = [_id - 1 if idx >= self.NUM_NODES_A and _id == self.kb - 1 else
        #                      _id for idx, _id in enumerate(n_id)]
        #         elif ka - self.ka < 0 and kb - self.kb < 0:
        #             _n_id = []
        #             for idx, _id in enumerate(n_id):
        #                 if idx < self.NUM_NODES_A and _id == self.ka - 1:
        #                     _n_id.append(_id - 1)
        #                 elif idx >= self.NUM_NODES_A and _id == self.kb - 1:
        #                     _n_id.append(_id - 1)
        #                 else:
        #                     _n_id.append(_id)
        #         else:
        #             _n_id = n_id
        #         new_of_group = [b_id if idx < self.NUM_NODES_A else b_id + ka for idx, b_id in enumerate(_n_id)]
        #         self._save_of_group_to_file(membership_path_, new_of_group)
        #     else:
        #         self._save_of_group_to_file(membership_path_, self.confident_of_group[(ka, kb)])

        params_ = ""
        if self.mcmc_cooling_ in ["exponential", "linear", "logarithmic"]:
            params_ = self.mcmc_cooling_param_1 + " " + self.mcmc_cooling_param_2
        elif self.mcmc_cooling_ == "constant":
            params_ = self.mcmc_cooling_param_1

        # n_blocks_ = " ".join(
        #     self._constrained_sum_sample_pos(ka, self.NUM_NODES_A)
        # ) + " " + " ".join(
        #     self._constrained_sum_sample_pos(kb, self.NUM_NODES_B)
        # )
        n_blocks_ = self._gen_init_n_blocks(self.NUM_NODES_A, self.NUM_NODES_B, ka, kb)

        #first time of calculation -- save an edgelist file for future use:


        n_types_ = str(self.NUM_NODES_A) + " " + str(self.NUM_NODES_B)
        action_list = [
            self.f_mcmc,
            "-e",
            self.f_edgelist_,
            "-n",
            n_blocks_,
            # "--membership_path",
            # membership_path_,  # just a temporary path, holding the configuration information
            "-t",
            str(self.mcmc_steps_),
            "-x",
            str(self.mcmc_await_steps_),
            "--maximize",
            "-c",
            self.mcmc_cooling_,
            "-a",
            params_,
            # "-r",  # initial random assignment or not
            "-y",
            n_types_,
            "-z",
            str(ka) + " " + str(kb),
            "-E",
            self.mcmc_epsilon_,
            "--randomize"
        ]

        action_str = ' '.join(action_list)
        # print action_str

        return action_str

    @staticmethod
    def _save_of_group_to_file(path, of_group):
        """Save the group membership list to a file path.

        Parameters
        ----------
        path : str, required
            File path for the list to save to.

        of_group : list[int], required
            Group membership list.
        """
        num_nodes = len(of_group)
        with open(path, "wb") as f:
            for i in range(0, num_nodes):
                f.write(str(of_group[i]) + "\n")
        return

    @retry(stop_max_attempt_number=10)
    def _engine(self, ka, kb):  # TODO: bug when assigned verbose=False
        """Run the shell code.

        Parameters
        ----------
        ka : int, required
            Number of communities for type-a nodes to partition.

        kb : int, required
            Number of communities for type-b nodes to partition.
        """

        action_str = self.prepare_engine(ka, kb)
        num_sweeps_ = 1

        def _run_engine(_):
            p = self._subprocess.Popen(
                action_str.split(' '),
                bufsize=2048,
                stdout=self._subprocess.PIPE
            )
            out, err = p.communicate()
            p.wait()
            return out, err, p

        num_sweep_ = 0

        while num_sweep_ < num_sweeps_:
            out, err, p = _run_engine("")
            if p.returncode == -11:  # when Exception raises from the mcmc code
                raise RuntimeError("Exception from C++ program during inference! -- " + action_str)
            elif p.returncode == 0:
                num_sweep_ += 1
                of_group = out.replace(' \n', '').split(' ')  # Note the space before the line break
                of_group = map(int, of_group)

        # try:
        #     self._os.remove(self.membership_path)
        # except Exception as e:
        #     print e
        # else:
        #     pass

        return of_group

    @staticmethod
    def _constrained_sum_sample_pos(n, total):
        # in this setting, there will be no empty groups generated by this function
        n = int(n)
        total = int(total)
        normalized_list = [int(total) + 1]
        while sum(normalized_list) > total and np.greater_equal(normalized_list, np.zeros(n)).all():
            indicator = True
            while indicator:
                normalized_list = list(map(round, map(lambda x: x * total, np.random.dirichlet(np.ones(n), 1).tolist()[0])))
                normalized_list = list(map(int, normalized_list))
                indicator = len(normalized_list) - np.count_nonzero(normalized_list) != 0
            sum_ = 0
            for ind, q in enumerate(normalized_list):
                if ind < len(normalized_list) - 1:
                    sum_ += q
            # TODO: there is a bug here; sometimes it assigns -1 to the end of the array, but pass the while condition
            normalized_list[len(normalized_list) - 1] = abs(total - sum_)
        assert sum(normalized_list) == total, "ERROR: the constrainedSumSamplePos-sampled list does not sum to #edges."
        return map(str, normalized_list)


    @staticmethod
    def _gen_init_n_blocks(NUM_NODES_A, NUM_NODES_B, KA, KB):
        num_nodes_A = np.arange(NUM_NODES_A)
        n_blocks_A = map(len, np.array_split(num_nodes_A, KA))
        num_nodes_B = np.arange(NUM_NODES_B)
        n_blocks_B = map(len, np.array_split(num_nodes_B, KB))

        n_blocks_ = " ".join(map(str, n_blocks_A)) + " " + " ".join(map(str, n_blocks_B))

        return n_blocks_

    # start from here: our main algorithm!
    @staticmethod
    @jit
    def _cal_italic_I(m_e_rs):
        italic_i = 0.
        m_e_r = np.sum(m_e_rs, axis=1)
        num_edges = m_e_r.sum() / 2.
        for ind, e_val in enumerate(np.nditer(m_e_rs)):
            ind_i = int(round(ind / (m_e_rs.shape[0])))
            ind_j = ind % (m_e_rs.shape[0])
            if e_val != 0.0:
                italic_i += e_val / 2. / num_edges * math.log(
                    e_val / m_e_r[ind_i] / m_e_r[ind_j] * 2 * num_edges
                )
        return italic_i

    @jit
    def _cal_desc_len(self, ka, kb, italic_i):
        desc_len_b = (
            self.NUM_NODES_A * self._math.log(ka) + self.NUM_NODES_B * self._math.log(kb) - self.NUM_EDGES * italic_i
        ) / self.NUM_EDGES
        x = float(ka * kb) / self.NUM_EDGES
        desc_len_b += (1 + x) * self._math.log(1 + x) - x * self._math.log(x)
        return desc_len_b


    @staticmethod
    @jit
    def m_e_rs_from_of_group(edgelist, of_group):
        # construct e_rs matrix
        m_e_rs = np.zeros((max(of_group) + 1, max(of_group) + 1))
        # print of_group
        for i in edgelist:
            # Please do check the index convention of the edgelist
            source_group = int(of_group[int(i[0])])
            target_group = int(of_group[int(i[1])])
            if source_group == target_group:
                raise StandardError("This is not a bipartite network!")
            m_e_rs[source_group][target_group] += 1
            m_e_rs[target_group][source_group] += 1

        m_e_r = np.sum(m_e_rs, axis=1)
        return m_e_rs, m_e_r

    @staticmethod
    def _permute_m_e_rs_and_get_index(m_e_rs):
        pass


    @staticmethod
    def _reduced_matrix(ka, kb, m_e_rs):
        # check if symmetric
        assert np.all(m_e_rs.transpose() == m_e_rs), "Error: input m_e_rs matrix is not symmetric!"
        from_row = random.sample([0] * ka + [ka] * kb, 1)[0]
        a = m_e_rs[0:ka, ka:ka+kb]

        merge_list = list([0, 0])    # which two of_group label should be merged together?
        of_group_map = OrderedDict()
        new_ka = 0
        new_kb = 0
        if from_row == 0:
            perm = np.arange(a.shape[0])
            np.random.shuffle(perm)
            for _ind in np.arange(a.shape[0]):
                of_group_map[_ind] = perm[_ind]
            a = a[perm]

            new_ka = ka - 1
            new_kb = kb
            b = np.zeros([new_ka, new_kb])
            for ind_i, _a in enumerate(a):
                for ind_j, __a in enumerate(_a):
                    if ind_i < from_row:
                        b[ind_i][ind_j] = __a
                    elif ind_i > from_row + 1:
                        b[ind_i - 1][ind_j] = __a
                    elif ind_i == from_row:
                        b[ind_i][ind_j] += __a
                    elif ind_i == from_row + 1:
                        b[ind_i - 1][ind_j] += __a

            merge_list[0] = of_group_map[from_row]
            merge_list[1] = of_group_map[from_row + 1]

        elif from_row == ka:
            perm = np.arange(a.shape[1])
            np.random.shuffle(perm)
            for _ind in np.arange(a.shape[1]):
                of_group_map[_ind] = perm[_ind]

            new_ka = ka
            new_kb = kb - 1
            a = a.transpose()

            a = a[perm]

            b = np.zeros([new_kb, new_ka])
            for ind_i, _a in enumerate(a):
                for ind_j, __a in enumerate(_a):
                    if ind_i < from_row - new_ka:
                        b[ind_i][ind_j] = __a
                    elif ind_i > from_row + 1 - new_ka:
                        b[ind_i - 1][ind_j] = __a
                    elif ind_i == from_row - new_ka:
                        b[ind_i][ind_j] += __a
                    elif ind_i == from_row + 1 - new_ka:
                        b[ind_i - 1][ind_j] += __a
            merge_list[0] = of_group_map[from_row - ka] + ka
            merge_list[1] = of_group_map[from_row + 1 - ka] + ka

        c = np.zeros([new_ka + new_kb, new_ka + new_kb])
        bt = b.transpose()
        if not from_row == 0:
            b = bt
            bt = b.transpose()
        for ind_i, _c in enumerate(c):
            for ind_j, __c in enumerate(_c):
                if ind_i >= new_ka and ind_j < new_ka:
                    c[ind_i][ind_j] = bt[ind_i - new_ka][ind_j]
                elif ind_i < new_ka and ind_j >= new_ka:
                    c[ind_i][ind_j] = b[ind_i][ind_j - new_ka]

        assert new_ka + new_kb == c.shape[0], "new_ka = {}; new_kb = {}; new_mat.shape[0] = {}".format(
            new_ka, new_kb, c.shape[0]
        )
        assert new_ka + new_kb == c.shape[1], "new_ka = {}; new_kb = {}; new_mat.shape[1] = {}".format(
            new_ka, new_kb, c.shape[1]
        )
        assert np.all(c.transpose() == c), "Error: output m_e_rs matrix is not symmetric!"
        # print "merge_list: ", merge_list
        return new_ka, new_kb, c, merge_list

    def _calc_with_hook(self, ka, kb, **kwargs):
        """
        Summary line.

        Extended description of function.

        Parameters
        ----------
        arg1 : int
            Description of arg1
        arg2 : str
            Description of arg2

        Returns
        -------
        italic_i : float
            Description of return value
        dist : float

        m_e_rs : numpy array


        """
        # each time when you calculate/search at particular ka and kb
        # the hood records relevant information for research
        try:
            self.confident_desc_len[(ka, kb)]
        except KeyError as _:
            pass
        else:
            italic_i = self.confident_italic_I[(ka, kb)]
            m_e_rs = self.confident_m_e_rs[(ka, kb)]
            of_group = self.confident_of_group[(ka, kb)]
            return italic_i, m_e_rs, of_group

        def _run_(ka, kb):
            of_group = self._engine(ka, kb)
            m_e_rs, _ = self.m_e_rs_from_of_group(self.edgelist, of_group)
            italic_i = self._cal_italic_I(m_e_rs)
            new_desc_len = self._cal_desc_len(ka, kb, italic_i)
            # print "new_desc_len = ", new_desc_len
            return m_e_rs, italic_i, new_desc_len, of_group

        def __par_run__(num_cores, num_sweeps):
            return self._Pool(num_cores=num_cores).map(lambda x: _run_(ka, kb), range(num_sweeps))

        # Calculate the biSBM inference several times,
        # choose the maximum likelihood result.
        # In other words, we choose the state with minimum entropy.
        results = []
        try:
            old_desc_len = float(kwargs["old_desc_len"])
        except KeyError as _:
            if self.PARALLELIZATION:
                # print "num_cores_", self.NUM_CORES
                # print "num_sweeps_", self.MAX_NUM_SWEEPS
                results = __par_run__(self.NUM_CORES, self.MAX_NUM_SWEEPS)
            else:
                results = [_run_(ka, kb)]
        else:  # TODO: better way of writing?
            if not self.PARALLELIZATION:
                # if old_desc_len is passed
                # we compare the new_desc_len with the old one
                # --
                # this option is used when we want to decide whether
                # we should escape from the local minimum during the heuristic
                calculate_times = 0
                while calculate_times < self.MAX_NUM_SWEEPS:
                    result = _run_(ka, kb)
                    results.append(result)
                    new_desc_len = self._cal_desc_len(ka, kb, result[1])
                    if new_desc_len < old_desc_len:
                        # no need to go further
                        calculate_times = self.MAX_NUM_SWEEPS
                    else:
                        calculate_times += 1
            else:
                results = __par_run__(self.NUM_CORES, self.MAX_NUM_SWEEPS)

        result = min(results, key=lambda x: x[2])
        of_group = result[3]
        italic_i = result[1]
        m_e_rs = result[0]

        return italic_i, m_e_rs, of_group

    def _moving_one_step_down(self, ka, kb):
        # print "confident_desc_len = " + str(self.confident_desc_len)
        # print "confident_italic_I = " + str(self.confident_italic_I)
        try:
            self.INIT_ITALIC_I
        except AttributeError as _:
            # This is an important step, where we
            # (1) Calculate the heavy biSBM at init (ka, kb)
            # (2) Initiate important variables for logging and drawing
            italic_i, m_e_rs, of_group = self._calc_with_hook(ka, kb)

            self.INIT_ITALIC_I = italic_i
            self.m_e_rs = m_e_rs

            # These confident_* variable are used to store "true" data
            # that is, not the sloppy temporarily results via matrix merging
            self.confident_desc_len[(ka, kb)] = self._cal_desc_len(ka, kb, italic_i)
            self.confident_m_e_rs[(ka, kb)] = m_e_rs
            self.confident_italic_I[(ka, kb)] = italic_i
            self.confident_of_group[(ka, kb)] = of_group
            self._save_of_group_info(ka, kb)

            # these are used to track temporarily variables during the heuristic
            self.diff_italic_I_array = [0.]
            self.ka_array = [ka]
            self.kb_array = [kb]

        def _sample_and_merge():
            _ka, _kb, _m_e_rs, _mlist = self._reduced_matrix(self.ka, self.kb, self.m_e_rs)
            _italic_I = self._cal_italic_I(_m_e_rs)
            diff_italic_i = _italic_I - self.INIT_ITALIC_I
            return _ka, _kb, _m_e_rs, diff_italic_i, _mlist

        indexes_to_run_ = range(0, (ka + kb) * 2)  # how many times that a sample merging takes place

        results = []
        for _ in indexes_to_run_:
            results.append(_sample_and_merge())

        __ka, __kb, __m_e_rs, diff_italic_i, _mlist = max(results, key=lambda x: x[3])

        assert int(__m_e_rs.sum()) == int(self.NUM_EDGES * 2), "__m_e_rs.sum() = {}; self.NUM_EDGES * 2 = {}".format(
            str(int(__m_e_rs.sum())), str(self.NUM_EDGES * 2)
        )

        # print("After reducing the matrix via merging we reached (ka, kb) = (%s, %s)", str(__ka), str(__kb))
        return __ka, __kb, __m_e_rs, diff_italic_i, _mlist

    def iterator(self):
        ka_moving = self.ka
        kb_moving = self.kb

        while ka_moving != 1 or kb_moving != 1:
            old_ka_moving = ka_moving
            old_kb_moving = kb_moving

            ka_moving, kb_moving, t_m_e_rs, diff_italic_i, mlist = self._moving_one_step_down(ka_moving, kb_moving)
            print(
                "Now trying (Ka, Kb) = ({}, {}) from (Ka, Kb) = ({}, {}) ...".format(
                    ka_moving, kb_moving, old_ka_moving,old_kb_moving
            ))
            if abs(diff_italic_i) > self.ITALIC_I_THRESHOLD * self.INIT_ITALIC_I:
                old_desc_len = self._calc_and_update((old_ka_moving, old_kb_moving))
                if any(i < old_desc_len for i in self.confident_desc_len.values()):
                    ka_moving, kb_moving = self._back_to_where_desc_len_is_lowest(diff_italic_i)
                else:
                    candidate_desc_len = self._calc_and_update((ka_moving, kb_moving), old_desc_len)
                    t_m_e_rs_cand = self.confident_m_e_rs[(ka_moving, kb_moving)]
                    if candidate_desc_len > old_desc_len:  # candidate move is not a good choice
                        tmp = [
                            ka_moving - old_ka_moving,
                            kb_moving - old_kb_moving
                        ]
                        tmp.reverse()
                        ka_moving = old_ka_moving + tmp[0]
                        kb_moving = old_kb_moving + tmp[1]
                        candidate_desc_len = self._calc_and_update((ka_moving, kb_moving), old_desc_len)
                        t_m_e_rs_cand = self.confident_m_e_rs[(ka_moving, kb_moving)]
                        if candidate_desc_len > old_desc_len:  # candidate move is not a good choice
                            ka_moving = old_ka_moving - 1
                            kb_moving = old_kb_moving - 1
                            candidate_desc_len = self._calc_and_update((ka_moving, kb_moving), old_desc_len)
                            t_m_e_rs_cand = self.confident_m_e_rs[(ka_moving, kb_moving)]
                            if candidate_desc_len > old_desc_len:  # candidate move is not a good choice
                                # Before we conclude anything,
                                # we check all the other points near here.
                                items = map(lambda x: (
                                    x[0] + old_ka_moving,
                                    x[1] + old_kb_moving
                                ), [(1, 0), (0, 1), (1, -1), (-1, 1), (+1, +1)]
                                            )
                                for item in items:
                                    self._calc_and_update(item, old_desc_len)
                                # print "done calculation on less probable points"

                                if any(i < old_desc_len for i in self.confident_desc_len.values()):
                                    print "New suspected point found...."
                                    self._back_to_where_desc_len_is_lowest(diff_italic_i)
                                else:
                                    print("DONE: the answer is...", old_ka_moving, old_kb_moving)

                                    # clean up
                                    self._os.remove(self.f_edgelist_)

                                    return self.confident_desc_len
                            else:
                                # continue moving with the
                                # new candidate's direction
                                self.ITALIC_I_THRESHOLD = float(self._ITALIC_I_THRESHOLD)
                                self._update_current_state((ka_moving, kb_moving), t_m_e_rs_cand)
                        else:
                            # continue moving w/ the new candidate's direction
                            self._update_current_state((ka_moving, kb_moving), t_m_e_rs_cand)
                    else:
                        # candidate-1 might be a good choice, but ....
                        # continue moving w/ the new candidate's direction
                        self._update_current_state((ka_moving, kb_moving), t_m_e_rs_cand)
            else:
                old_of_g = self.confident_of_group[(self.ka, self.kb)]
                new_of_g = list(np.zeros(self.NUM_NODES))
                # new_of_g = [i - 1 if i > ind else i for i in old_of_g]
                # print "mlist", mlist
                mlist.sort()
                for _node_id, _g in enumerate(old_of_g):
                    if _g == mlist[1]:
                        new_of_g[_node_id] = mlist[0]
                    elif _g <= mlist[0]:
                        new_of_g[_node_id] = _g
                    else:
                        new_of_g[_node_id] = _g - 1

                # inntermediate state infos
                self.confident_of_group[(ka_moving, kb_moving)] = new_of_g
                self._save_of_group_info(ka_moving, kb_moving)
                # self.confident_italic_I[(ka_moving, kb_moving)] = self._cal_italic_I(t_m_e_rs)
                # self.confident_desc_len[(ka_moving, kb_moving)] = self._cal_desc_len(
                #     ka_moving, kb_moving, self.confident_italic_I[(ka_moving, kb_moving)]
                # )

                # print("-- merging mat just prevented expansive biSBM calculation --")
                self._update_current_state((ka_moving, kb_moving), t_m_e_rs)

            # for drawing...
            self._iter_calc_hook(diff_italic_i)
        return

    def _save_of_group_info(self, ka, kb):
        self.confident_of_group_info[(ka, kb)] = {}
        for block_id in self.confident_of_group[(ka, kb)]:
            try:
                self.confident_of_group_info[(ka, kb)][block_id]
            except KeyError:
                self.confident_of_group_info[(ka, kb)][block_id] = 0
                self.confident_of_group_info[(ka, kb)][block_id] += 1
            else:
                self.confident_of_group_info[(ka, kb)][block_id] += 1
        # sanity check
        assert sum(self.confident_of_group_info[(ka, kb)].values()) == self.NUM_NODES
        return self.confident_of_group_info[(ka, kb)]

    def _back_to_where_desc_len_is_lowest(self, diff_italic_i):
        # print("You are going too far, the (ka, kb) around here are too small.")
        self._iter_calc_hook(diff_italic_i)
        self.ka = sorted(self.confident_desc_len, key=self.confident_desc_len.get, reverse=False)[0][0]
        self.kb = sorted(self.confident_desc_len, key=self.confident_desc_len.get, reverse=False)[0][1]
        # print("assigned new starting (ka, kb) to", self.ka, self.kb)
        self.ITALIC_I_THRESHOLD *= 0.9
        self.m_e_rs = self.confident_m_e_rs[(self.ka, self.kb)]
        return self.ka, self.kb

    def _iter_calc_hook(self, diff_italic_i):
        self.diff_italic_I_array.append(diff_italic_i)
        self.ka_array.append(self.ka)
        self.kb_array.append(self.kb)
        return

    def _update_current_state(self, point, m_e_rs):
        # print("Find new direction!! Assign new m_e_rs...")
        self.ka = point[0]
        self.kb = point[1]
        # this will be used in _moving_one_step_down function
        self.m_e_rs = m_e_rs
        return

    def _calc_and_update(self, point, old_desc_len=0):
        if old_desc_len == 0:
            italic_i, m_e_rs, of_group = self._calc_with_hook(point[0], point[1])
        else:
            italic_i, m_e_rs, of_group = self._calc_with_hook(point[0], point[1], old_desc_len=old_desc_len)
        candidate_desc_len = self._cal_desc_len(point[0], point[1], italic_i)
        self.confident_italic_I[point] = italic_i
        self.confident_m_e_rs[point] = m_e_rs
        self.confident_desc_len[point] = candidate_desc_len
        self.confident_of_group[point] = of_group
        self._save_of_group_info(point[0], point[1])
        return candidate_desc_len