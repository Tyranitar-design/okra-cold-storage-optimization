# Baseline v3.0 Capacity-Chain Report

## Solver

- status: TIME_LIMIT
- solution_count: 10
- objective: 4205367.9926100625
- objective_bound: 3948575.5827972246
- mip_gap_pct: 6.106300572603626
- claim_state: feasible_time_limit_incumbent
- allowed_claim: The v3.0 run can be cited as a feasible incumbent with an open MIP gap (6.1063%), not as a proven optimum.

## Summary

- total_cost: 4205367.9926100625
- fixed_cost: 3330000.0
- operate_cost: 734000.0
- transport_cost: 46893.28093774236
- loss_cost: 94128.98331835776
- carbon_cost: 345.728353962366
- num_facilities: 6
- total_annual_production_ton: 588.1834248373999
- total_service_annual_flow_ton: 1176.3668496747998
- total_peak_capacity_load_ton: 156.2607298651359
- installed_capacity_ton: 175
- fresh_chain_share: 0.9
- frozen_or_processing_share: 0.1
- downstream_share_sum: 1.0
- capacity_semantics: peak_inventory_from_annual_flow
- selected_storage_types: ['ca', 'cold', 'frozen', 'precool']

## Checks

- solver_status: state=feasible_gap_open, detail=status=TIME_LIMIT, sol_count=10, objective=4205367.993, bound=3948575.583, gap=6.1063%
- capacity_semantics: state=corrected, detail=peak_load=156.261t, installed_capacity=175.000t
- temperature_chain: state=corrected, detail=selected_storage_types=['ca', 'cold', 'frozen', 'precool']
- frozen_cap: state=corrected, detail=frozen_or_processing_share=0.100

## Channel Mix

- precool: annual_flow=588.183t, share=50.00%, peak_load=0.980t
- cold: annual_flow=352.910t, share=30.00%, peak_load=49.407t
- ca: annual_flow=176.455t, share=15.00%, peak_load=70.582t
- frozen: annual_flow=58.818t, share=5.00%, peak_load=35.291t

## Boundary

This report packages the v3.0 corrected baseline. It improves capacity and service-chain semantics, but channel shares remain scenario assumptions until real enterprise or official channel data are ingested.
