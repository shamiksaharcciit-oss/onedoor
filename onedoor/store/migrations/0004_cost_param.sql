-- Which parameter carries the money, per action type.
--
-- Euro caps are evaluated against a cost. Until now that cost could only come
-- from the caller setting `cost_eur` on the request, and an integration that
-- did not set it -- including the LangGraph tool wrapper shipped in examples --
-- produced a cost of zero for every call. Every euro cap then compared
-- 0 + 0 > limit and permitted everything, silently, with a clean audit trail.
--
-- Declaring the parameter in policy puts the money control where every other
-- bound already lives, and lets the engine refuse when it cannot resolve an
-- amount instead of assuming there is none.

ALTER TABLE policies ADD COLUMN cost_param TEXT;
