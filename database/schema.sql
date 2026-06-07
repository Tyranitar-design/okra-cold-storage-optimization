-- 秋葵冷库优化项目 PostgreSQL/PostGIS schema v1
-- Purpose: support research-grade evidence tracking, optimization experiments,
-- map visualization, AI-Benders traces, SPO datasets, and logistics integration.

begin;

create extension if not exists postgis;
create extension if not exists pgcrypto;

create schema if not exists okra;

-- ---------------------------------------------------------------------------
-- 1. Evidence and provenance
-- ---------------------------------------------------------------------------

create table if not exists okra.data_sources (
    source_id text primary key,
    source_name text not null,
    source_type text not null,
    evidence_level text not null check (evidence_level in ('A', 'B', 'C', 'D', 'E', 'F', 'C/D')),
    file_path_or_url text,
    access_date date,
    license_or_permission text,
    variables text,
    preprocessing text,
    limitations text,
    used_in text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists okra.literature_sources (
    literature_id text primary key,
    title text not null,
    authors text,
    year integer,
    journal_or_source text,
    doi text,
    url text,
    evidence_level text not null default 'D',
    local_path text,
    citation_style text,
    notes text,
    created_at timestamptz not null default now()
);

create table if not exists okra.parameter_evidence (
    parameter_id uuid primary key default gen_random_uuid(),
    stable_key text,
    parameter_name text not null,
    parameter_value numeric,
    parameter_unit text,
    source_id text references okra.data_sources(source_id) on update cascade,
    literature_id text references okra.literature_sources(literature_id) on update cascade,
    model_usage text,
    confidence_note text,
    created_at timestamptz not null default now()
);

create table if not exists okra.artifact_registry (
    artifact_id uuid primary key default gen_random_uuid(),
    stable_key text,
    artifact_type text not null,
    artifact_name text not null,
    file_path text not null,
    generating_script text,
    source_ids text[],
    experiment_id uuid,
    claim_supported text,
    limitations text,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 2. Spatial and business data
-- ---------------------------------------------------------------------------

create table if not exists okra.nodes (
    node_id text primary key,
    name text not null,
    level integer not null,
    level_name text,
    lat numeric(10, 7) not null,
    lon numeric(10, 7) not null,
    geom geometry(Point, 4326) generated always as (
        st_setsrid(st_makepoint(lon::double precision, lat::double precision), 4326)
    ) stored,
    okra_production_ton numeric(12, 4) not null default 0,
    is_candidate boolean not null default false,
    population numeric(14, 4),
    road_access boolean,
    source_id text references okra.data_sources(source_id) on update cascade,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists okra.candidate_sites (
    site_id text primary key,
    node_id text not null references okra.nodes(node_id) on update cascade on delete cascade,
    site_status text not null default 'candidate',
    site_type text not null default 'node_candidate',
    source_id text references okra.data_sources(source_id) on update cascade,
    notes text,
    created_at timestamptz not null default now()
);

create table if not exists okra.cold_storage_types (
    type_code text primary key,
    type_name text not null,
    temp_min_c numeric(8, 3),
    temp_max_c numeric(8, 3),
    energy_kwh_per_ton numeric(12, 4),
    carbon_factor numeric(12, 6),
    source_id text references okra.data_sources(source_id) on update cascade,
    notes text
);

create table if not exists okra.capacity_options (
    capacity_option_id uuid primary key default gen_random_uuid(),
    type_code text not null references okra.cold_storage_types(type_code) on update cascade on delete cascade,
    capacity_ton numeric(12, 4) not null,
    fixed_cost_wan numeric(14, 4) not null,
    operate_cost_wan_per_year numeric(14, 4) not null,
    variable_cost_yuan_per_ton numeric(14, 4),
    source_id text references okra.data_sources(source_id) on update cascade,
    unique (type_code, capacity_ton)
);

create table if not exists okra.distance_matrix (
    origin_node_id text not null references okra.nodes(node_id) on update cascade on delete cascade,
    destination_node_id text not null references okra.nodes(node_id) on update cascade on delete cascade,
    distance_km numeric(14, 6) not null,
    source_id text references okra.data_sources(source_id) on update cascade,
    primary key (origin_node_id, destination_node_id)
);

create table if not exists okra.transport_time_matrix (
    origin_node_id text not null references okra.nodes(node_id) on update cascade on delete cascade,
    destination_node_id text not null references okra.nodes(node_id) on update cascade on delete cascade,
    time_h numeric(14, 6) not null,
    source_id text references okra.data_sources(source_id) on update cascade,
    primary key (origin_node_id, destination_node_id)
);

-- ---------------------------------------------------------------------------
-- 2b. Real external data extensions
-- ---------------------------------------------------------------------------

create table if not exists okra.market_price_observations (
    price_observation_id uuid primary key default gen_random_uuid(),
    source_id text not null references okra.data_sources(source_id) on update cascade,
    observation_date date not null,
    commodity_name text not null,
    market_name text not null default '',
    province text not null default '',
    price_yuan_per_kg numeric(14, 6),
    price_index numeric(14, 6),
    unit_original text,
    raw_record_json jsonb not null default '{}'::jsonb,
    raw_file_path text,
    source_url text,
    ingested_at timestamptz not null default now(),
    unique (source_id, observation_date, commodity_name, market_name, province)
);

create table if not exists okra.weather_daily_observations (
    weather_observation_id uuid primary key default gen_random_uuid(),
    source_id text not null references okra.data_sources(source_id) on update cascade,
    observation_date date not null,
    station_id text not null,
    station_name text,
    lat numeric(10, 7) not null,
    lon numeric(10, 7) not null,
    geom geometry(Point, 4326) generated always as (
        st_setsrid(st_makepoint(lon::double precision, lat::double precision), 4326)
    ) stored,
    temperature_mean_c numeric(10, 4),
    temperature_max_c numeric(10, 4),
    temperature_min_c numeric(10, 4),
    relative_humidity_pct numeric(10, 4),
    precipitation_mm numeric(12, 4),
    wind_speed_m_s numeric(12, 4),
    raw_record_json jsonb not null default '{}'::jsonb,
    raw_file_path text,
    source_url text,
    ingested_at timestamptz not null default now(),
    unique (source_id, observation_date, station_id)
);

create table if not exists okra.osm_features (
    osm_feature_id uuid primary key default gen_random_uuid(),
    source_id text not null references okra.data_sources(source_id) on update cascade,
    osm_id text not null,
    feature_type text not null,
    name text,
    highway text,
    amenity text,
    shop text,
    building text,
    lat numeric(10, 7),
    lon numeric(10, 7),
    geometry_geojson jsonb not null default '{}'::jsonb,
    tags_json jsonb not null default '{}'::jsonb,
    raw_file_path text,
    source_url text,
    ingested_at timestamptz not null default now(),
    unique (source_id, osm_id, feature_type)
);

create table if not exists okra.road_network_edges (
    road_edge_id uuid primary key default gen_random_uuid(),
    source_id text not null references okra.data_sources(source_id) on update cascade,
    edge_key text not null,
    from_osm_id text,
    to_osm_id text,
    highway text,
    road_name text,
    length_m numeric(14, 4),
    assumed_speed_kmh numeric(10, 4),
    travel_time_min numeric(14, 4),
    geometry_geojson jsonb not null default '{}'::jsonb,
    tags_json jsonb not null default '{}'::jsonb,
    raw_file_path text,
    source_url text,
    ingested_at timestamptz not null default now(),
    unique (source_id, edge_key)
);

-- ---------------------------------------------------------------------------
-- 3. Optimization experiments and solutions
-- ---------------------------------------------------------------------------

create table if not exists okra.optimization_experiments (
    experiment_id uuid primary key default gen_random_uuid(),
    experiment_key text not null unique,
    name text not null,
    model_type text not null,
    data_version text,
    model_version text,
    status text not null default 'created',
    config_json jsonb not null default '{}'::jsonb,
    notes text,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz
);

create table if not exists okra.optimization_runs (
    run_id uuid primary key default gen_random_uuid(),
    experiment_id uuid not null references okra.optimization_experiments(experiment_id) on delete cascade,
    run_key text not null unique,
    solver_name text,
    solver_version text,
    license_type text,
    time_limit_sec numeric(12, 3),
    mip_gap_target numeric(12, 8),
    mip_gap_actual numeric(12, 8),
    threads integer,
    status_code integer,
    status_name text,
    runtime_sec numeric(14, 6),
    raw_result_path text,
    created_at timestamptz not null default now()
);

create table if not exists okra.solution_metrics (
    run_id uuid primary key references okra.optimization_runs(run_id) on delete cascade,
    total_cost_yuan numeric(18, 6),
    fixed_cost_yuan numeric(18, 6),
    operate_cost_yuan numeric(18, 6),
    transport_cost_yuan numeric(18, 6),
    loss_cost_yuan numeric(18, 6),
    carbon_cost_yuan numeric(18, 6),
    transport_loss_ton numeric(14, 6),
    storage_loss_ton numeric(14, 6),
    static_carbon_ton numeric(14, 6),
    dynamic_carbon_ton numeric(14, 6),
    num_facilities integer,
    precool_violations integer,
    demand_total_ton numeric(14, 6),
    cost_per_ton numeric(14, 6),
    extra_metrics jsonb not null default '{}'::jsonb
);

create table if not exists okra.solution_facilities (
    solution_facility_id uuid primary key default gen_random_uuid(),
    run_id uuid not null references okra.optimization_runs(run_id) on delete cascade,
    site_id text not null,
    type_code text not null,
    capacity_ton numeric(12, 4),
    capacity_idx integer,
    fixed_cost_wan numeric(14, 4),
    operate_cost_wan_per_year numeric(14, 4),
    assigned_demand_ton numeric(14, 6),
    utilization_pct numeric(10, 4),
    unique (run_id, site_id, type_code, capacity_ton)
);

create table if not exists okra.solution_assignments (
    assignment_id uuid primary key default gen_random_uuid(),
    run_id uuid not null references okra.optimization_runs(run_id) on delete cascade,
    demand_node_id text not null references okra.nodes(node_id) on update cascade,
    facility_site_id text not null,
    type_code text,
    assigned_ton numeric(14, 6),
    distance_km numeric(14, 6),
    transport_time_h numeric(14, 6),
    loss_ton numeric(14, 6),
    carbon_ton numeric(14, 6)
);

create table if not exists okra.sensitivity_results (
    sensitivity_id uuid primary key default gen_random_uuid(),
    result_key text,
    run_id uuid references okra.optimization_runs(run_id) on delete cascade,
    scenario_name text,
    sweep_variable text not null,
    sweep_value numeric(18, 6) not null,
    total_cost_yuan numeric(18, 6),
    num_facilities integer,
    runtime_sec numeric(14, 6),
    metrics_json jsonb not null default '{}'::jsonb
);

create table if not exists okra.pareto_solutions (
    pareto_id uuid primary key default gen_random_uuid(),
    run_id uuid references okra.optimization_runs(run_id) on delete cascade,
    solution_key text,
    cost_yuan numeric(18, 6),
    loss_ton numeric(14, 6),
    carbon_ton numeric(14, 6),
    epsilon_loss numeric(14, 6),
    epsilon_carbon numeric(14, 6),
    is_nondominated boolean not null default true,
    solution_json jsonb not null default '{}'::jsonb
);

create table if not exists okra.method_runs (
    run_key text primary key,
    method_name text not null,
    status_code integer,
    objective numeric(18, 6),
    metric_1 numeric(18, 8),
    metric_2 numeric(18, 8),
    runtime_sec numeric(14, 6),
    note text,
    source_path text,
    metrics_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 4. Benders / AI-Benders / SPO traces
-- ---------------------------------------------------------------------------

create table if not exists okra.benders_iterations (
    iteration_id uuid primary key default gen_random_uuid(),
    run_id uuid not null references okra.optimization_runs(run_id) on delete cascade,
    iter_no integer not null,
    lower_bound numeric(18, 6),
    upper_bound numeric(18, 6),
    gap_pct numeric(14, 6),
    cuts_added integer,
    runtime_sec numeric(14, 6),
    notes text,
    unique (run_id, iter_no)
);

create table if not exists okra.ai_benders_cut_scores (
    cut_score_id uuid primary key default gen_random_uuid(),
    run_id uuid not null references okra.optimization_runs(run_id) on delete cascade,
    iter_no integer not null,
    cut_id text not null,
    cut_type text,
    features_json jsonb not null default '{}'::jsonb,
    score numeric(18, 8),
    selected boolean not null default false,
    policy_name text,
    unique (run_id, iter_no, cut_id)
);

create table if not exists okra.spo_training_runs (
    spo_run_id uuid primary key default gen_random_uuid(),
    run_key text not null unique,
    model_type text,
    data_source_id text references okra.data_sources(source_id) on update cascade,
    dataset_path text,
    sample_count integer,
    alpha_r2 numeric(12, 6),
    beta_r2 numeric(12, 6),
    alpha_rmse numeric(12, 6),
    beta_rmse numeric(12, 6),
    alpha_mae numeric(12, 6),
    beta_mae numeric(12, 6),
    model_paths jsonb not null default '{}'::jsonb,
    prediction_paths jsonb not null default '{}'::jsonb,
    feature_columns jsonb not null default '[]'::jsonb,
    target_columns jsonb not null default '[]'::jsonb,
    limitations text,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 5. Logistics integration
-- ---------------------------------------------------------------------------

create table if not exists okra.logistics_integration_jobs (
    job_id uuid primary key default gen_random_uuid(),
    job_key text not null unique,
    run_id uuid references okra.optimization_runs(run_id) on delete set null,
    logistics_base_url text,
    request_payload jsonb not null default '{}'::jsonb,
    response_payload jsonb not null default '{}'::jsonb,
    status text not null default 'created',
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

-- ---------------------------------------------------------------------------
-- 6. Enterprise data placeholders
-- ---------------------------------------------------------------------------

create table if not exists okra.enterprise_batches (
    batch_id text primary key,
    anonymized_org text,
    origin_node_id text references okra.nodes(node_id) on update cascade,
    harvest_time timestamptz,
    weight_ton numeric(14, 6),
    grade text,
    source_id text references okra.data_sources(source_id) on update cascade,
    created_at timestamptz not null default now()
);

create table if not exists okra.enterprise_storage_logs (
    storage_log_id uuid primary key default gen_random_uuid(),
    batch_id text references okra.enterprise_batches(batch_id) on update cascade on delete cascade,
    storage_id text,
    temperature_c numeric(8, 3),
    humidity_pct numeric(8, 3),
    in_time timestamptz,
    out_time timestamptz,
    source_id text references okra.data_sources(source_id) on update cascade
);

create table if not exists okra.enterprise_transport_logs (
    transport_log_id uuid primary key default gen_random_uuid(),
    batch_id text references okra.enterprise_batches(batch_id) on update cascade on delete cascade,
    vehicle_id text,
    origin_node_id text references okra.nodes(node_id) on update cascade,
    destination_node_id text references okra.nodes(node_id) on update cascade,
    depart_time timestamptz,
    arrive_time timestamptz,
    distance_km numeric(14, 6),
    source_id text references okra.data_sources(source_id) on update cascade
);

create table if not exists okra.enterprise_quality_records (
    quality_record_id uuid primary key default gen_random_uuid(),
    batch_id text references okra.enterprise_batches(batch_id) on update cascade on delete cascade,
    loss_weight_ton numeric(14, 6),
    spoilage_rate numeric(12, 8),
    quality_score numeric(12, 6),
    inspection_time timestamptz,
    source_id text references okra.data_sources(source_id) on update cascade
);

-- Incremental compatibility for databases initialized with earlier schema drafts.
alter table if exists okra.parameter_evidence add column if not exists stable_key text;
alter table if exists okra.artifact_registry add column if not exists stable_key text;
alter table if exists okra.sensitivity_results add column if not exists result_key text;
alter table if exists okra.spo_training_runs add column if not exists model_type text;
alter table if exists okra.spo_training_runs add column if not exists alpha_rmse numeric(12, 6);
alter table if exists okra.spo_training_runs add column if not exists beta_rmse numeric(12, 6);
alter table if exists okra.spo_training_runs add column if not exists prediction_paths jsonb not null default '{}'::jsonb;
alter table if exists okra.spo_training_runs add column if not exists feature_columns jsonb not null default '[]'::jsonb;
alter table if exists okra.spo_training_runs add column if not exists target_columns jsonb not null default '[]'::jsonb;

-- ---------------------------------------------------------------------------
-- 7. Indexes for high-frequency filters and joins
-- ---------------------------------------------------------------------------

create unique index if not exists parameter_evidence_stable_key_uix on okra.parameter_evidence (stable_key);
create unique index if not exists artifact_registry_stable_key_uix on okra.artifact_registry (stable_key);
create unique index if not exists sensitivity_results_key_uix on okra.sensitivity_results (result_key);
create index if not exists nodes_geom_gix on okra.nodes using gist (geom);
create index if not exists nodes_candidate_idx on okra.nodes (is_candidate);
create index if not exists nodes_level_idx on okra.nodes (level);
create index if not exists candidate_sites_node_idx on okra.candidate_sites (node_id);
create index if not exists distance_matrix_destination_idx on okra.distance_matrix (destination_node_id);
create index if not exists transport_time_matrix_destination_idx on okra.transport_time_matrix (destination_node_id);
create index if not exists market_price_date_idx on okra.market_price_observations (observation_date);
create index if not exists market_price_commodity_idx on okra.market_price_observations (commodity_name);
create index if not exists weather_daily_date_idx on okra.weather_daily_observations (observation_date);
create index if not exists weather_daily_station_idx on okra.weather_daily_observations (station_id);
create index if not exists weather_daily_geom_gix on okra.weather_daily_observations using gist (geom);
create index if not exists osm_features_type_idx on okra.osm_features (feature_type);
create index if not exists osm_features_osm_idx on okra.osm_features (osm_id);
create index if not exists road_network_edges_key_idx on okra.road_network_edges (edge_key);
create index if not exists optimization_experiments_model_type_idx on okra.optimization_experiments (model_type);
create index if not exists optimization_runs_experiment_idx on okra.optimization_runs (experiment_id);
create index if not exists solution_facilities_run_idx on okra.solution_facilities (run_id);
create index if not exists solution_assignments_run_idx on okra.solution_assignments (run_id);
create index if not exists solution_assignments_demand_idx on okra.solution_assignments (demand_node_id);
create index if not exists sensitivity_results_sweep_idx on okra.sensitivity_results (sweep_variable, sweep_value);
create index if not exists benders_iterations_run_idx on okra.benders_iterations (run_id, iter_no);
create index if not exists ai_benders_cut_scores_run_idx on okra.ai_benders_cut_scores (run_id, iter_no);
create index if not exists logistics_jobs_run_idx on okra.logistics_integration_jobs (run_id);

-- ---------------------------------------------------------------------------
-- 8. MIS Phase 2 tables (route plans, audit logs, users)
-- ---------------------------------------------------------------------------

create table if not exists okra.users (
    id              uuid primary key default gen_random_uuid(),
    username        varchar(50) unique not null,
    hashed_password varchar(255) not null,
    display_name    varchar(100),
    role            varchar(20) not null default 'viewer'
                    check (role in ('admin', 'analyst', 'viewer')),
    is_active       boolean not null default true,
    created_at      timestamp not null default now()
);

-- Seed users (bcrypt hashes — replace with your actual hashes)
-- insert into okra.users (username, hashed_password, display_name, role) values
--   ('admin', '$2b$12$...', '管理员', 'admin'),
--   ('analyst', '$2b$12$...', '分析师', 'analyst'),
--   ('viewer', '$2b$12$...', '访客', 'viewer')
-- on conflict (username) do update set hashed_password = excluded.hashed_password;

create table if not exists okra.route_plans (
    id                uuid primary key default gen_random_uuid(),
    name              varchar(100) not null,
    description       text,
    status            varchar(20) not null default 'draft'
                      check (status in ('draft', 'active', 'archived')),
    total_distance_km numeric(10, 2),
    total_cost_yuan   numeric(12, 2),
    vehicle_type      varchar(32),
    created_by        varchar(50),
    created_at        timestamp not null default now(),
    updated_at        timestamp not null default now()
);

create table if not exists okra.route_stops (
    id                uuid primary key default gen_random_uuid(),
    route_plan_id     uuid not null
                      references okra.route_plans(id) on delete cascade,
    stop_order        int not null,
    node_id           text references okra.nodes(node_id),
    action            varchar(20) not null default 'delivery'
                      check (action in ('pickup', 'delivery', 'transit')),
    planned_arrival   timestamp,
    planned_departure timestamp,
    notes             text
);

create index if not exists route_stops_plan_idx on okra.route_stops (route_plan_id);

create table if not exists okra.operation_logs (
    id          uuid primary key default gen_random_uuid(),
    user_id     varchar(50),
    action      varchar(50),
    target_type varchar(50),
    target_id   varchar(100),
    detail      jsonb not null default '{}'::jsonb,
    created_at  timestamp not null default now()
);

create index if not exists operation_logs_user_idx on okra.operation_logs (user_id);
create index if not exists operation_logs_created_idx on okra.operation_logs (created_at);

commit;
