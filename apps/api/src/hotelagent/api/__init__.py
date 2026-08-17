"""The vocabulary every console endpoint shares.

Not a module in the `modules/` sense — it owns no tables and no business rules.
It exists so that "how do you ask for page two" and "how do you say which city
is asking" are answered once, in one place, rather than per router.

That matters more than it sounds. The console generates its types from our
OpenAPI document, so an endpoint that spells pagination differently forces a
second table component in the frontend, and an endpoint that forgets city
scoping is a tenancy bug that looks like a normal handler in review.
"""
