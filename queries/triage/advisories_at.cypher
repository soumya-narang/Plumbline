// Advisories published by $at_ms, oldest first. Params: $at_ms
MATCH (adv:Advisory)
WHERE adv.published_ms <= $at_ms
RETURN adv.id AS advisory, adv.package AS package, adv.published_ms AS published_ms, adv.summary AS summary
ORDER BY published_ms, advisory
