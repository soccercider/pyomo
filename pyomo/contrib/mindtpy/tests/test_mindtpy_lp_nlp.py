"""Tests for the MINDT solver plugin."""
from math import fabs
import pyomo.core.base.symbolic
import pyutilib.th as unittest
from pyomo.contrib.mindtpy.tests.eight_process_problem import \
    EightProcessFlowsheet
from pyomo.contrib.mindtpy.tests.MINLP_simple import SimpleMINLP as SimpleMINLP
from pyomo.contrib.mindtpy.tests.MINLP2_simple import SimpleMINLP as SimpleMINLP2
from pyomo.contrib.mindtpy.tests.MINLP3_simple import SimpleMINLP as SimpleMINLP3
from pyomo.contrib.mindtpy.tests.from_proposal import ProposalModel
from pyomo.contrib.mindtpy.tests.online_doc_example import OnlineDocExample
from pyomo.environ import SolverFactory, value
from pyomo.opt import TerminationCondition

required_solvers = ('ipopt', 'cplex_persistent')
if all(SolverFactory(s).available(False) for s in required_solvers):
    subsolvers_available = True
else:
    subsolvers_available = False


@unittest.skipIf(not subsolvers_available,
                 "Required subsolvers %s are not available"
                 % (required_solvers,))
@unittest.skipIf(not pyomo.core.base.symbolic.differentiate_available,
                 "Symbolic differentiation is not available")
class TestMindtPy(unittest.TestCase):
    """Tests for the MindtPy solver plugin."""

    # lazy callback tests

    def test_lazy_OA_8PP(self):
        """Test the outer approximation decomposition algorithm."""
        with SolverFactory('mindtpy') as opt:
            model = EightProcessFlowsheet()
            print('\n Solving problem with Outer Approximation')
            results = opt.solve(model, strategy='OA',
                                init_strategy='rNLP',
                                mip_solver=required_solvers[1],
                                nlp_solver=required_solvers[0],
                                bound_tolerance=1E-5,
                                single_tree=True)

            self.assertIs(results.solver.termination_condition,
                          TerminationCondition.optimal)
            self.assertAlmostEqual(value(model.cost.expr), 68, places=1)

    def test_lazy_OA_8PP_init_max_binary(self):
        """Test the outer approximation decomposition algorithm."""
        with SolverFactory('mindtpy') as opt:
            model = EightProcessFlowsheet()
            print('\n Solving problem with Outer Approximation')
            results = opt.solve(model, strategy='OA',
                                init_strategy='max_binary',
                                mip_solver=required_solvers[1],
                                nlp_solver=required_solvers[0],
                                single_tree=True)

            self.assertIs(results.solver.termination_condition,
                          TerminationCondition.optimal)
            self.assertAlmostEqual(value(model.cost.expr), 68, places=1)

    def test_lazy_OA_MINLP_simple(self):
        """Test the outer approximation decomposition algorithm."""
        with SolverFactory('mindtpy') as opt:
            model = SimpleMINLP()
            print('\n Solving problem with Outer Approximation')
            results = opt.solve(model, strategy='OA',
                                init_strategy='initial_binary',
                                mip_solver=required_solvers[1],
                                nlp_solver=required_solvers[0],
                                obj_bound=10,
                                single_tree=True)

            self.assertIs(results.solver.termination_condition,
                          TerminationCondition.optimal)
            self.assertAlmostEqual(value(model.cost.expr), 3.5, places=2)

    def test_lazy_OA_MINLP2_simple(self):
        """Test the outer approximation decomposition algorithm."""
        with SolverFactory('mindtpy') as opt:
            model = SimpleMINLP2()
            print('\n Solving problem with Outer Approximation')
            results = opt.solve(model, strategy='OA',
                                init_strategy='initial_binary',
                                mip_solver=required_solvers[1],
                                nlp_solver=required_solvers[0],
                                obj_bound=10,
                                single_tree=True)

            self.assertIs(results.solver.termination_condition,
                          TerminationCondition.optimal)
            self.assertAlmostEqual(value(model.cost.expr), 6.00976, places=2)

    def test_lazy_OA_MINLP3_simple(self):
        """Test the outer approximation decomposition algorithm."""
        with SolverFactory('mindtpy') as opt:
            model = SimpleMINLP3()
            print('\n Solving problem with Outer Approximation')
            results = opt.solve(model, strategy='OA', init_strategy='initial_binary',
                                mip_solver=required_solvers[1],
                                nlp_solver=required_solvers[0],
                                obj_bound=10,
                                single_tree=True)

            self.assertIs(results.solver.termination_condition,
                          TerminationCondition.optimal)
            self.assertAlmostEqual(value(model.cost.expr), -5.512, places=2)

    def test_lazy_OA_Proposal(self):
        """Test the outer approximation decomposition algorithm."""
        with SolverFactory('mindtpy') as opt:
            model = ProposalModel()
            print('\n Solving problem with Outer Approximation')
            results = opt.solve(model, strategy='OA',
                                mip_solver=required_solvers[1],
                                nlp_solver=required_solvers[0],
                                single_tree=True)

            self.assertIs(results.solver.termination_condition,
                          TerminationCondition.optimal)
            self.assertAlmostEqual(value(model.obj.expr), 0.66555, places=2)

    def test_OA_OnlineDocExample(self):
        with SolverFactory('mindtpy') as opt:
            model = OnlineDocExample()
            print('\n Solving problem with Outer Approximation')
            results = opt.solve(model, strategy='OA',
                                mip_solver=required_solvers[1],
                                nlp_solver=required_solvers[0],
                                single_tree=True
                                )

            self.assertIs(results.solver.termination_condition,
                          TerminationCondition.optimal)
            self.assertAlmostEqual(value(model.objective.expr), 3, places=2)

    # TODO fix the bug with integer_to_binary
    # def test_OA_Proposal_with_int_cuts(self):
    #     """Test the outer approximation decomposition algorithm."""
    #     with SolverFactory('mindtpy') as opt:
    #         model = ProposalModel()
    #         print('\n Solving problem with Outer Approximation')
    #         opt.solve(model, strategy='OA',
    #                   mip_solver=required_solvers[1],
    #                   nlp_solver=required_solvers[0],
    #                   add_integer_cuts=True,
    #                   integer_to_binary=True,  # if we use lazy callback, we cannot set integer_to_binary True
    #                   lazy_callback=True,
    #                   iteration_limit=1)

    #         # self.assertIs(results.solver.termination_condition,
    #         #               TerminationCondition.optimal)
    #         self.assertAlmostEquals(value(model.obj.expr), 0.66555, places=2)


if __name__ == "__main__":
    unittest.main()
