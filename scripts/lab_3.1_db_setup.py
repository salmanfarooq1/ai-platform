import psycopg2

# create a connection to our postgres database, so we can query and do operations
# if not running, just do docker-compose up -d in the terminal
# the database here is the database inside postgres, it can have many databases
# we need to provide the host and the port ( for now it is localhost, if running on some other server, we would provide the IP of that server)
conn = psycopg2.connect(

    host = 'localhost',
    port = 5432,
    database = 'postgres',
    user = 'postgres',
    password = 'postgres'
)

# to be able to communicate with our db through python, we need to create a cursor object.

cursor = conn.cursor()

# for any query, transaction, or any operation, we simply use .execute() function of the cursor

# for the very first, we need to enable pgvector extension, we do that by below query, IF NOT EXISTS makes it safe to run multiple times

cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')

# now we create a table with two columns, embeddings column has a data type of "vector(128)", which is 128 D vector datatype ( in python, a list containing 128 elements)

cursor.execute('CREATE TABLE IF NOT EXISTS test_table ( id SERIAL PRIMARY KEY, embeddings vector(128))')

# now we insert one row to test the insert functionality (%s is parsed by SQL itself, it puts the first value after comma)
# we insert a tuple of list with 128 elements as embedding

cursor.execute('INSERT INTO test_table (embeddings) VALUES (%s)', ([0.1] * 128 ,))

# we commit after every transaction, commit() makes permanent changes, but if not committed, above operations would be rolled back.

conn.commit()

# now we query to see if our above operations worked

cursor.execute('SELECT id, embeddings FROM test_table LIMIT 1')

# fetchone() fetches the first result

results = cursor.fetchone()
print(results)

# now we close the cursor and the connection as well

cursor.close()
conn.close()