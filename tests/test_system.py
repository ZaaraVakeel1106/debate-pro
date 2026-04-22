import unittest
from models import *

class TestSystem(unittest.TestCase):

    def test_user_creation(self):
        add_user({'username':'test','password':'123','role':'admin'})
        users = get_users()
        self.assertTrue(len(users) > 0)

    def test_match_generation(self):
        generate_matches()
        matches = get_matches()
        self.assertTrue(len(matches) >= 0)

    def test_score(self):
        submit_score({'team':'A','points':80})
        data = get_leaderboard()
        self.assertTrue(len(data) >= 0)

if __name__ == '__main__':
    unittest.main()