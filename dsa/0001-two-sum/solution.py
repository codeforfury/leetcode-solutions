class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:

        # Dictionary to store:
        # number -> its index
        seen = {}

        for i in range(len(nums)):

            # Find the number we need
            complement = target - nums[i]

            # If complement already exists,
            # we found the two numbers
            if complement in seen:
                return [seen[complement], i]

            # Store the current number and its index
            seen[nums[i]] = i