try:
    import pymysql
    pymysql.version_info = (2, 2, 7, "final", 0)
    pymysql.install_as_MySQLdb()
except Exception:
    # pymysql is optional; if not installed the project will continue to work with SQLite
    pass
