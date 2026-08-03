pub const W_MIN: f64 = 0.0;
pub const W_MAX: f64 = 1.0;
pub const DEFAULT_SAFE_DT: f64 = 0.01;
pub const MAX_SLEW_RATE: f64 = 0.5;

#[repr(C)]
pub struct PhoenixInputPacket {
    pub current_weight: f64,
    pub target_weight: f64,
    pub dt: f64,
}

#[repr(C)]
pub struct PhoenixOutputPacket {
    pub next_weight: f64,
    pub delta_applied: f64,
    pub status_code: i32, // 0 = CONVERGING, 1 = AT_EQUILIBRIUM, 2 = POLICY_FALLBACK
}

#[no_mangle]
pub extern "C" fn phoenix_a_core_step(input: PhoenixInputPacket) -> PhoenixOutputPacket {
    // Step 1: Policy Sanitization
    let dt_valid = if input.dt.is_finite() && input.dt > 0.0 {
        input.dt
    } else {
        DEFAULT_SAFE_DT
    };

    let curr_is_valid = input.current_weight.is_finite();
    let tgt_is_valid = input.target_weight.is_finite();
    let dt_is_valid = input.dt.is_finite() && input.dt > 0.0;

    let fallback_triggered = !(curr_is_valid && tgt_is_valid && dt_is_valid);

    let curr = if curr_is_valid { input.current_weight } else { W_MIN };
    let tgt = if tgt_is_valid { input.target_weight } else { W_MIN };

    // Step 2: Hard Geometric Clamp
    let curr_clamped = curr.clamp(W_MIN, W_MAX);
    let tgt_clamped = tgt.clamp(W_MIN, W_MAX);

    // Step 3: Equilibrium Check (<= 1e-9 matching Python reference)
    if (curr_clamped - tgt_clamped).abs() <= 1e-9 {
        return PhoenixOutputPacket {
            next_weight: tgt_clamped,
            delta_applied: 0.0,
            status_code: if fallback_triggered { 2 } else { 1 },
        };
    }

    // Step 4: Slew Bounding
    let max_delta_step = MAX_SLEW_RATE * dt_valid;
    let raw_delta = tgt_clamped - curr_clamped;

    let applied_delta = if raw_delta > 0.0 {
        raw_delta.min(max_delta_step)
    } else {
        raw_delta.max(-max_delta_step)
    };

    let next_w = curr_clamped + applied_delta;
    let bounded_w = if raw_delta > 0.0 {
        next_w.min(tgt_clamped)
    } else {
        next_w.max(tgt_clamped)
    };

    let final_weight = bounded_w.clamp(W_MIN, W_MAX);

    PhoenixOutputPacket {
        next_weight: final_weight,
        delta_applied: final_weight - curr_clamped,
        status_code: if fallback_triggered { 2 } else { 0 },
    }
}