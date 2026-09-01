class Solution:
    def isPalindrome(self, x: int) -> bool:

        # Negative numbers are not palindromes
        if x < 0:
            return False

        # Store the original number
        original = x

        # Variable to store the reversed number
        reverse = 0

        # Reverse the number
        while x > 0:
            digit = x % 10
            reverse = reverse * 10 + digit
            x = x // 10

        # Compare original and reversed number
        return original == reverse