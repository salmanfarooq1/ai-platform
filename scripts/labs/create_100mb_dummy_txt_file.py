with open('test_data/100mb_dummy_file.txt', 'w') as f:
    for _ in range(100_000):  # 100k lines
        f.write('x' * 1000 + '\n')  # ~1KB per line