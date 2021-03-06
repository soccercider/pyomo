"""Master problem functions."""
from __future__ import division

from pyomo.contrib.gdpopt.util import copy_var_list_values
from pyomo.core import Constraint, Expression, Objective, minimize, value, Var
from pyomo.opt import TerminationCondition as tc
from pyomo.opt import SolutionStatus, SolverFactory
from pyomo.contrib.gdpopt.util import SuppressInfeasibleWarning, _DoNothing
from pyomo.contrib.gdpopt.mip_solve import distinguish_mip_infeasible_or_unbounded
from pyomo.solvers.plugins.solvers.persistent_solver import PersistentSolver

from pyomo.contrib.mindtpy.nlp_solve import (solve_NLP_subproblem,
                                             handle_NLP_subproblem_optimal, handle_NLP_subproblem_infeasible,
                                             handle_NLP_subproblem_other_termination, solve_NLP_feas)
from pyomo.contrib.mindtpy.cut_generation import (add_oa_cuts,
                                                  add_int_cut)
from pyomo.contrib.gdpopt.util import copy_var_list_values, identify_variables
from math import copysign
from pyomo.environ import *
from pyomo.core import Constraint, minimize, value
from pyomo.core.expr import current as EXPR
from math import fabs

from pyomo.repn import generate_standard_repn

from pyomo.common.dependencies import attempt_import

single_tree, single_tree_available = attempt_import(
    'pyomo.contrib.mindtpy.single_tree')


def solve_OA_master(solve_data, config):
    solve_data.mip_iter += 1
    MindtPy = solve_data.mip.MindtPy_utils
    config.logger.info(
        'MIP %s: Solve master problem.' %
        (solve_data.mip_iter,))
    # Set up MILP
    for c in MindtPy.constraint_list:
        if c.body.polynomial_degree() not in (1, 0):
            c.deactivate()

    MindtPy.MindtPy_linear_cuts.activate()
    main_objective = next(
        solve_data.mip.component_data_objects(Objective, active=True))
    main_objective.deactivate()

    sign_adjust = 1 if main_objective.sense == minimize else - 1
    MindtPy.del_component('MindtPy_oa_obj')

    if config.add_slack:
        MindtPy.del_component('MindtPy_penalty_expr')

        MindtPy.MindtPy_penalty_expr = Expression(
            expr=sign_adjust * config.OA_penalty_factor * sum(
                v for v in MindtPy.MindtPy_linear_cuts.slack_vars[...]))

        MindtPy.MindtPy_oa_obj = Objective(
            expr=main_objective.expr + MindtPy.MindtPy_penalty_expr,
            sense=main_objective.sense)
    else:
        MindtPy.MindtPy_oa_obj = Objective(
            expr=main_objective.expr,
            sense=main_objective.sense)
    # Deactivate extraneous IMPORT/EXPORT suffixes
    getattr(solve_data.mip, 'ipopt_zL_out', _DoNothing()).deactivate()
    getattr(solve_data.mip, 'ipopt_zU_out', _DoNothing()).deactivate()

    masteropt = SolverFactory(config.mip_solver)
    # determine if persistent solver is called.
    if isinstance(masteropt, PersistentSolver):
        masteropt.set_instance(solve_data.mip, symbolic_solver_labels=True)
    if config.single_tree:
        # Configuration of lazy callback
        lazyoa = masteropt._solver_model.register_callback(
            single_tree.LazyOACallback_cplex)
        # pass necessary data and parameters to lazyoa
        lazyoa.master_mip = solve_data.mip
        lazyoa.solve_data = solve_data
        lazyoa.config = config
        lazyoa.opt = masteropt
        masteropt._solver_model.set_warning_stream(None)
        masteropt._solver_model.set_log_stream(None)
        masteropt._solver_model.set_error_stream(None)
        masteropt.options['timelimit'] = config.time_limit
    master_mip_results = masteropt.solve(
        solve_data.mip, **config.mip_solver_args)  # , tee=True)

    if master_mip_results.solver.termination_condition is tc.optimal:
        if config.single_tree:
            if main_objective.sense == minimize:
                solve_data.LB = max(
                    master_mip_results.problem.lower_bound, solve_data.LB)
                solve_data.LB_progress.append(solve_data.LB)

                solve_data.UB = min(
                    master_mip_results.problem.upper_bound, solve_data.UB)
                solve_data.UB_progress.append(solve_data.UB)

    elif master_mip_results.solver.termination_condition is tc.infeasibleOrUnbounded:
        # Linear solvers will sometimes tell me that it's infeasible or
        # unbounded during presolve, but fails to distinguish. We need to
        # resolve with a solver option flag on.
        master_mip_results, _ = distinguish_mip_infeasible_or_unbounded(
            solve_data.mip, config)

    return solve_data.mip, master_mip_results


def handle_master_mip_optimal(master_mip, solve_data, config, copy=True):
    """Copy the result to working model and update upper or lower bound"""
    # proceed. Just need integer values
    MindtPy = master_mip.MindtPy_utils
    main_objective = next(
        master_mip.component_data_objects(Objective, active=True))
    # check if the value of binary variable is valid
    for var in MindtPy.variable_list:
        if var.value == None:
            config.logger.warning(
                "Variables {} not initialized are set to it's lower bound when using the initial_binary initialization method".format(var.name))
            var.value = 0  # nlp_var.bounds[0]
    copy_var_list_values(
        master_mip.MindtPy_utils.variable_list,
        solve_data.working_model.MindtPy_utils.variable_list,
        config)

    if main_objective.sense == minimize:
        solve_data.LB = max(
            value(MindtPy.MindtPy_oa_obj.expr), solve_data.LB)
        solve_data.LB_progress.append(solve_data.LB)
    else:
        solve_data.UB = min(
            value(MindtPy.MindtPy_oa_obj.expr), solve_data.UB)
        solve_data.UB_progress.append(solve_data.UB)
    config.logger.info(
        'MIP %s: OBJ: %s  LB: %s  UB: %s'
        % (solve_data.mip_iter, value(MindtPy.MindtPy_oa_obj.expr),
           solve_data.LB, solve_data.UB))


def handle_master_mip_other_conditions(master_mip, master_mip_results, solve_data, config):
    if master_mip_results.solver.termination_condition is tc.infeasible:
        handle_master_mip_infeasible(master_mip, solve_data, config)
    elif master_mip_results.solver.termination_condition is tc.unbounded:
        handle_master_mip_unbounded(master_mip, solve_data, config)
    elif master_mip_results.solver.termination_condition is tc.maxTimeLimit:
        handle_master_mip_max_timelimit(master_mip, solve_data, config)
    elif (master_mip_results.solver.termination_condition is tc.other and
            master_mip_results.solution.status is SolutionStatus.feasible):
        # load the solution and suppress the warning message by setting
        # solver status to ok.
        MindtPy = master_mip.MindtPy_utils
        config.logger.info(
            'MILP solver reported feasible solution, '
            'but not guaranteed to be optimal.')
        copy_var_list_values(
            master_mip.MindtPy_utils.variable_list,
            solve_data.working_model.MindtPy_utils.variable_list,
            config)
        if MindtPy.obj.sense == minimize:
            solve_data.LB = max(
                value(MindtPy.MindtPy_oa_obj.expr), solve_data.LB)
            solve_data.LB_progress.append(solve_data.LB)
        else:
            solve_data.UB = min(
                value(MindtPy.MindtPy_oa_obj.expr), solve_data.UB)
            solve_data.UB_progress.append(solve_data.UB)
        config.logger.info(
            'MIP %s: OBJ: %s  LB: %s  UB: %s'
            % (solve_data.mip_iter, value(MindtPy.MindtPy_oa_obj.expr),
               solve_data.LB, solve_data.UB))
    else:
        raise ValueError(
            'MindtPy unable to handle MILP master termination condition '
            'of %s. Solver message: %s' %
            (master_mip_results.solver.termination_condition, master_mip_results.solver.message))


def handle_master_mip_infeasible(master_mip, solve_data, config):
    config.logger.info(
        'MILP master problem is infeasible. '
        'Problem may have no more feasible '
        'binary configurations.')
    if solve_data.mip_iter == 1:
        config.logger.warning(
            'MindtPy initialization may have generated poor '
            'quality cuts.')
    # set optimistic bound to infinity
    main_objective = next(
        master_mip.component_data_objects(Objective, active=True))
    if main_objective.sense == minimize:
        solve_data.LB = float('inf')
        solve_data.LB_progress.append(solve_data.UB)
    else:
        solve_data.UB = float('-inf')
        solve_data.UB_progress.append(solve_data.UB)


def handle_master_mip_max_timelimit(master_mip, solve_data, config):
    # TODO check that status is actually ok and everything is feasible
    MindtPy = master_mip.MindtPy_utils
    config.logger.info(
        'Unable to optimize MILP master problem '
        'within time limit. '
        'Using current solver feasible solution.')
    copy_var_list_values(
        master_mip.MindtPy_utils.variable_list,
        solve_data.working_model.MindtPy_utils.variable_list,
        config)
    if MindtPy.obj.sense == minimize:
        solve_data.LB = max(
            value(MindtPy.obj.expr), solve_data.LB)
        solve_data.LB_progress.append(solve_data.LB)
    else:
        solve_data.UB = min(
            value(MindtPy.obj.expr), solve_data.UB)
        solve_data.UB_progress.append(solve_data.UB)
    config.logger.info(
        'MIP %s: OBJ: %s  LB: %s  UB: %s'
        % (solve_data.mip_iter, value(MindtPy.obj.expr),
           solve_data.LB, solve_data.UB))


def handle_master_mip_unbounded(master_mip, solve_data, config):
    # Solution is unbounded. Add an arbitrary bound to the objective and resolve.
    # This occurs when the objective is nonlinear. The nonlinear objective is moved
    # to the constraints, and deactivated for the linear master problem.
    MindtPy = master_mip.MindtPy_utils
    config.logger.warning(
        'Master MILP was unbounded. '
        'Resolving with arbitrary bound values of (-{0:.10g}, {0:.10g}) on the objective. '
        'You can change this bound with the option obj_bound.'.format(config.obj_bound))
    main_objective = next(
        master_mip.component_data_objects(Objective, active=True))
    MindtPy.objective_bound = Constraint(
        expr=(-config.obj_bound, main_objective.expr, config.obj_bound))
    with SuppressInfeasibleWarning():
        opt = SolverFactory(config.mip_solver)
        if isinstance(opt, PersistentSolver):
            opt.set_instance(master_mip)
        master_mip_results = opt.solve(
            master_mip, **config.mip_solver_args)
