-- Optional vacuum thrust-time curve for each rocket stage.
-- Each point is [powered_time_seconds, vacuum_thrust_kN].
alter table public.rocket_stages
  add column if not exists thrust_curve_json jsonb;

comment on column public.rocket_stages.thrust_curve_json is
  'Optional vacuum thrust curve as [[powered_time_seconds, thrust_kN], ...], ordered from t=0.';

-- Strap-on solid motors need the same optional curve field (e.g. P160C).
alter table public.rocket_boosters
  add column if not exists thrust_curve_json jsonb;

comment on column public.rocket_boosters.thrust_curve_json is
  'Optional vacuum thrust curve as [[powered_time_seconds, thrust_kN], ...], ordered from t=0.';
