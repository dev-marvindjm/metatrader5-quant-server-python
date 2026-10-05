import unittest
from app.core.result import Ok, Err, Result, safe_exec


class TestResultMonad(unittest.TestCase):
    def test_ok_behavior(self):
        res: Result[int, str] = Ok(42)
        self.assertTrue(res.is_ok())
        self.assertFalse(res.is_err())
        self.assertEqual(res.unwrap(), 42)
        self.assertEqual(res.unwrap_or(0), 42)

        # map
        mapped = res.map(lambda x: x * 2)
        self.assertTrue(mapped.is_ok())
        self.assertEqual(mapped.unwrap(), 84)

        # and_then
        chained = res.and_then(lambda x: Ok(f"value: {x}"))
        self.assertTrue(chained.is_ok())
        self.assertEqual(chained.unwrap(), "value: 42")

    def test_err_behavior(self):
        res: Result[int, str] = Err("Something failed")
        self.assertFalse(res.is_ok())
        self.assertTrue(res.is_err())
        self.assertEqual(res.unwrap_err(), "Something failed")
        self.assertEqual(res.unwrap_or(999), 999)

        # map does nothing on Err
        mapped = res.map(lambda x: x * 2)
        self.assertTrue(mapped.is_err())
        self.assertEqual(mapped.unwrap_err(), "Something failed")

        # map_err
        mapped_err = res.map_err(lambda e: f"Error: {e}")
        self.assertTrue(mapped_err.is_err())
        self.assertEqual(mapped_err.unwrap_err(), "Error: Something failed")

    def test_safe_exec(self):
        def divide(a, b):
            return a / b

        res_ok = safe_exec(divide, 10, 2)
        self.assertTrue(res_ok.is_ok())
        self.assertEqual(res_ok.unwrap(), 5.0)

        res_err = safe_exec(divide, 10, 0)
        self.assertTrue(res_err.is_err())
        self.assertIsInstance(res_err.unwrap_err(), ZeroDivisionError)


if __name__ == "__main__":
    unittest.main()
