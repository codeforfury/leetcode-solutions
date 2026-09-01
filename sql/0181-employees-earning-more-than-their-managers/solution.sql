SELECT e.name as EMPLOYEE 
FROM Employee e JOIN Employee m
ON e.managerId = m.id
WHERE e.salary > m.salary;