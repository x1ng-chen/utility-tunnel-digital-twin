#ifndef UT_TEST_SUPPORT_H
#define UT_TEST_SUPPORT_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { uint32_t checks,failures,first_line,groups,done; } UtTestResults;
extern volatile UtTestResults ut_test_results;
void test_entry(void);
#ifdef __cplusplus
}
#endif
#define CHECK(condition) do { ++ut_test_results.checks; if(!(condition)) { \
  ++ut_test_results.failures; if(!ut_test_results.first_line)ut_test_results.first_line=__LINE__; } } while(0)
#define GROUP() (++ut_test_results.groups)
#endif
