def migrate(rows)
    for row in rows:
        yield row.upper()
