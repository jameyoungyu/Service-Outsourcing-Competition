/**
 * IndusOpt API TypeScript Types
 * Generated & Synchronized with backend/openapi.json (OpenAPI 3.1.0, Phase 3)
 */

export interface ErrorDetail {
  code: string;
  message: string;
  details?: Record<string, any> | null;
}

export interface ErrorEnvelope {
  success: false;
  data: null;
  error: ErrorDetail;
  request_id: string;
}

export interface SuccessEnvelope<T> {
  success: true;
  data: T;
  error: null;
  request_id: string;
}

export type ApiResponse<T> = SuccessEnvelope<T> | ErrorEnvelope;

/** Progress descriptor every long-running or completed stage returns. */
export interface TaskResource {
  task_id: string;
  status: string;
  stage: string;
  progress: number;
  message?: string | null;
}

// System API Types
export interface LivenessData {
  status: string;
  uptime_seconds: number;
}

export interface ComponentHealth {
  status: string;
  latency_ms?: number | null;
  error?: string | null;
}

export interface ReadinessData {
  status: string;
  components: {
    postgres: ComponentHealth;
    redis: ComponentHealth;
  };
}

export interface SystemInfoData {
  name: string;
  version: string;
  api_version: string;
  environment: string;
  docs_url: string;
  openapi_url: string;
}

// Simulation API Types
export interface SimulationGenerateRequest {
  scenario: "S1" | "S2" | "S3" | "S4" | "S5";
  dataset_name: string;
  num_samples?: number;
  noise_level?: number;
  seed?: number;
}

export interface DynamicSegmentGroundTruth {
  start_idx: number;
  end_idx: number;
  segment_type: string;
}

export interface SimulationGroundTruth {
  system_type: string;
  true_na: number;
  true_nb: number[];
  true_delays: number[];
  true_parameters: Record<string, number>;
  dynamic_segments: DynamicSegmentGroundTruth[];
  noise_level: number;
  seed: number;
}

export interface SimulationGenerateResponse {
  dataset_id: string;
  dataset_name: string;
  version_id: string;
  scenario: string;
  file_path: string;
  num_rows: number;
  num_cols: number;
  columns: string[];
  ground_truth: SimulationGroundTruth;
}

// Dataset API Types (Phase 3 Real Models)
export interface DatasetColumnInfo {
  name: string;
  data_type?: string;
  role: "time" | "input" | "output" | "ignored" | "timestamp" | "ignore";
  missing_count?: number;
  unit?: string | null;
}

export interface DatasetItem {
  id: string;
  name: string;
  version_id: string;
  latest_version_id?: string;
  source?: string;
  status?: string;
  file_size_bytes: number;
  row_count: number;
  col_count: number;
  column_count?: number;
  created_at: string;
  updated_at?: string;
  time_column: string;
  input_columns: string[];
  output_column: string | null;
  columns?: DatasetColumnInfo[];
  preview?: Record<string, any>[];
}

export interface DatasetListResponse {
  items: DatasetItem[];
  page?: {
    current_page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
}

export interface DatasetUploadResponse {
  dataset: DatasetItem;
  parse_task: {
    task_id: string;
    status: string;
    progress: number;
  };
  deduplicated: boolean;
}

export interface ColumnStatInfo {
  count: number;
  mean: number | null;
  std: number | null;
  min: number | null;
  max: number | null;
  q25: number | null;
  q50: number | null;
  q75: number | null;
}

export interface DatasetProfile {
  dataset_id: string;
  version_id: string;
  total_rows: number;
  total_cols: number;
  missing_rate: number;
  missing_rates: Record<string, number>;
  max_consecutive_missing?: number;
  anomaly_counts: Record<string, number>;
  interval_histogram: Array<{ bin: number; count: number }>;
  duplicate_timestamp_count?: number;
  irregular_sampling_rate?: number;
  frozen_segments?: number;
  constant_columns?: string[];
  time_range_start?: string | null;
  time_range_end?: string | null;
  sample_period_seconds?: number | null;
  column_statistics?: Record<string, ColumnStatInfo>;
  quality_score: number;
  recommendations: string[];
  quality_issues?: string[];
}

export interface DatasetVersionNode {
  version_id: string;
  parent_version_id?: string | null;
  operation_name: string;
  parameters?: Record<string, any>;
  created_at: string;
}

export interface DatasetVersionsResponse {
  dataset_id: string;
  active_version_id: string;
  nodes: DatasetVersionNode[];
  edges?: Array<{ source: string; target: string }>;
}

export interface DatasetDeleteResponse {
  dataset_id: string;
  status: string;
}

export interface DatasetColumnConfig {
  name: string;
  role: "time" | "input" | "output" | "ignored" | "timestamp" | "ignore";
  unit?: string | null;
}

export interface DatasetConfigRequest {
  columns?: DatasetColumnConfig[];
  time_column?: string;
  input_columns?: string[];
  output_column?: string | null;
  ignored_columns?: string[];
}

// Preprocessing API Types
export interface CleanRequest {
  dataset_id: string;
  version_id: string;
  resample_period_s?: number;
  interpolation_method?: "linear" | "ffill" | "bfill";
  outlier_method?: "hampel" | "iqr" | "zscore";
  hampel_window?: number;
  hampel_n_sigmas?: number;
}

export interface CleanResponse {
  dataset_id: string;
  new_version_id: string;
  raw_series: number[];
  cleaned_series: number[];
  replaced_indices: number[];
  total_cleaned_points: number;
}

export interface SegmentItem {
  segment_id: string;
  start_index: number;
  end_index: number;
  start_time?: string | null;
  end_time?: string | null;
  snr_db: number;
  dynamic_score: number;
  recommendation: string;
  /** Rank in the greedy selection order; 1 is the most informative segment. */
  rank?: number | null;
  /** Marginal Fisher-information gain contributed by this segment, in bits. */
  information_gain_bits?: number | null;
  cumulative_log_det?: number | null;
  n_rows?: number | null;
  missing_ratio?: number | null;
  anomaly_ratio?: number | null;
}

/** One candidate window the quality gate scored, whether or not it survived. */
export interface GatedWindow {
  window_index: number;
  start_index: number;
  end_index: number;
  missing_ratio: number;
  anomaly_ratio: number;
  snr_db: number;
  input_activity: number;
  output_activity: number;
  accepted: boolean;
  rejection_reasons: string[];
}

/** Information-theoretic outcome of the D-optimal stage. */
export interface SelectionSummary {
  candidate_count: number;
  gated_count: number;
  selected_count: number;
  selected_rows: number;
  coverage_ratio: number;
  baseline_log_det: number;
  selected_log_det: number;
  information_retention: number | null;
  evaluated_candidates: number;
  naive_candidate_evaluations: number;
  lazy_speedup: number;
  stopped_reason: string;
  condition_number: number | null;
  excitation_satisfied: boolean;
  persistent_excitation_order: Record<string, number>;
  required_excitation_order: Record<string, number>;
  rejection_counts: Record<string, number>;
  noise_sigma: number;
}

export interface SegmentRequest {
  version_id: string;
  input_columns: string[];
  output_column: string;
  dataset_id?: string | null;
  window_size?: number;
  stride?: number;
  max_segments?: number;
  min_snr_db?: number;
  na?: number;
  nb?: number;
  nk?: number;
  train_ratio?: number;
  max_missing_ratio?: number;
  max_anomaly_ratio?: number;
  min_input_activity_ratio?: number;
  min_information_gain_bits?: number;
}

export interface SegmentResponse {
  source_version_id: string;
  dataset_id: string | null;
  task: TaskResource;
  timestamps: string[];
  series: Record<string, (number | null)[]>;
  segments: SegmentItem[];
  selection: SelectionSummary | null;
  gated_windows: GatedWindow[];
  selected_indices: number[];
}

export interface DelayPeak {
  lag: number;
  correlation: number;
  confidence: number;
}

export interface DelayRequest {
  version_id: string;
  input_columns: string[];
  output_column: string;
  dataset_id?: string | null;
  max_lag?: number;
  top_k?: number;
}

export interface DelayResponse {
  source_version_id: string;
  dataset_id: string | null;
  task: TaskResource;
  delays: number[];
  /** Prewhitened cross-correlation curve per input, indexed by lag. */
  correlations: Record<string, number[]>;
  best_delays: Record<string, number>;
  candidate_peaks: Record<string, DelayPeak[]>;
  /** Validation free-run FIT achieved by the refined delay set. */
  validation_fit: number | null;
  refinement_rounds: number;
  /** Inputs whose top two candidates were too close to separate confidently. */
  uncertain_columns: string[];
  prewhitening_orders: Record<string, number>;
}

export interface VariableRecommendation {
  variable: string;
  action: "keep" | "drop" | "merge" | "review";
  reason: string;
  related_variables: string[];
}

export interface CollinearityRequest {
  version_id: string;
  input_columns: string[];
  dataset_id?: string | null;
  output_column?: string | null;
  correlation_threshold?: number;
  vif_threshold?: number;
}

export interface CollinearityResponse {
  source_version_id: string;
  dataset_id: string | null;
  task: TaskResource;
  variables: string[];
  matrix: number[][];
  spearman_matrix: number[][];
  vif_scores: Record<string, number>;
  condition_number: number | null;
  correlated_groups: string[][];
  recommendations: VariableRecommendation[];
}

// Modeling & Optimization API Types
export interface ARXFitRequest {
  dataset_id: string;
  version_id: string;
  na: number;
  nb: number[];
  delays: number[];
  estimation_method?: "ols" | "ridge";
  ridge_alpha?: number;
}

export interface ArxMetrics {
  train_r2: number | null;
  train_fit: number | null;
  train_rmse: number | null;
  val_r2: number | null;
  val_fit: number | null;
  val_rmse: number | null;
  test_r2: number | null;
  test_fit: number | null;
  test_rmse: number | null;
  rmse: number | null;
  mae: number | null;
  nrmse: number | null;
  /** Free-run (infinite-step) simulation FIT — the primary acceptance metric. */
  train_free_run_fit: number | null;
  val_free_run_fit: number | null;
  test_free_run_fit: number | null;
  aic: number | null;
  bic: number | null;
}

export interface ModelValidationData {
  one_step_fit: number | null;
  free_run_fit: number | null;
  free_run_rmse: number | null;
  /** one_step_fit - free_run_fit. A large gap means the model is coasting on persistence. */
  fit_gap: number | null;
  stable: boolean;
  max_pole_modulus: number | null;
  steady_state_gains: Record<string, number>;
  residual_whiteness_ratio: number | null;
  n_samples: number;
  partition: string;
}

export interface PriorViolation {
  variable: string;
  kind: "gain_sign" | "gain_bounds" | "stability";
  expected: string;
  actual: number | null;
}

export interface SplitIndices {
  train_end: number;
  val_end: number;
  test_end: number;
}

export interface ARXFitResponse {
  model_id: string;
  task: TaskResource;
  estimator: "ols" | "ridge";
  dataset_id: string | null;
  version_id: string | null;
  coefficients: Record<string, number>;
  a_coefficients: number[];
  b_coefficients: Record<string, number[]>;
  metrics: ArxMetrics;
  plot_data: {
    indices: number[];
    y_true: number[];
    y_pred: number[];
    residuals: number[];
    splits: SplitIndices;
    split_indices: SplitIndices | null;
  };
  residual_diagnostics: {
    acf_values: number[];
    confidence_interval: number | null;
  };
  artifact_uri: string | null;
  validation: ModelValidationData | null;
  prior_violations: PriorViolation[];
  training_rows: number;
  /** Model output driven by inputs alone, aligned with plot_data.indices. */
  free_run_series: number[];
}

export interface OptunaStartRequest {
  dataset_id: string;
  n_trials?: number;
  target_metric?: "fit" | "r2" | "rmse";
  search_space?: Record<string, any>;
}

export interface OptunaTrialItem {
  trial_id: number;
  value: number;
  params: Record<string, any>;
  state: "COMPLETE" | "PRUNED" | "FAIL";
}

export interface OptunaStatusResponse {
  study_id: string;
  status: "RUNNING" | "COMPLETED" | "CANCELLED" | "FAILED";
  current_trial: number;
  total_trials: number;
  best_value: number;
  best_params: Record<string, any>;
  trials: OptunaTrialItem[];
  convergence_curve: number[];
  param_importances: Record<string, number>;
}

// Copilot API Types
export interface CopilotStepNode {
  step_id: string;
  title: string;
  tool_name: string;
  status: "pending" | "running" | "waiting_confirmation" | "completed" | "failed";
  requires_hitl: boolean;
  impact_summary?: string | null;
}

export interface CopilotChatRequest {
  prompt: string;
  dataset_id?: string | null;
}

export interface CopilotChatResponse {
  session_id: string;
  reply_text: string;
  plan_nodes: CopilotStepNode[];
  active_step_id?: string | null;
}

export interface CopilotConfirmRequest {
  session_id: string;
  step_id: string;
  approved: boolean;
  custom_parameters?: Record<string, any>;
}
