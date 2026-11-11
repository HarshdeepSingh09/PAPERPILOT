import React, { useState, useEffect } from 'react';
import {
  Layers,
  CheckCircle2,
  XCircle,
  Sparkles,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Send,
  RotateCcw,
  Sliders,
  Award,
  AlertCircle,
  HelpCircle,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { DocumentItem, QuizData, QuizQuestion } from '../types';
import { studyApi } from '../api/client';

interface QuizViewProps {
  document: DocumentItem;
}

export const QuizView: React.FC<QuizViewProps> = ({ document }) => {
  const [quiz, setQuiz] = useState<QuizData | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [userAnswers, setUserAnswers] = useState<Record<number, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Configuration state
  const [numQuestions, setNumQuestions] = useState<number>(5);
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard' | 'mixed'>('medium');
  const [questionType, setQuestionType] = useState<'mcq' | 'true_false' | 'mixed'>('mixed');
  const [showConfig, setShowConfig] = useState(false);

  // Fetch latest quiz for this document on mount
  useEffect(() => {
    let isMounted = true;
    const loadLatestQuiz = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await studyApi.getLatestQuiz(document.id);
        if (isMounted && data) {
          setQuiz(data);
          // Pre-populate user answers if already completed
          if (data.completed) {
            const initial: Record<number, string> = {};
            data.questions.forEach((q) => {
              if (q.user_answer) initial[q.id] = String(q.user_answer);
            });
            setUserAnswers(initial);
          }
        }
      } catch (err: any) {
        if (isMounted) setQuiz(null);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadLatestQuiz();
    return () => {
      isMounted = false;
    };
  }, [document.id]);

  const handleGenerateQuiz = async (force = false) => {
    try {
      setIsLoading(true);
      setError(null);
      setShowConfig(false);
      setCurrentIndex(0);
      setUserAnswers({});
      const data = await studyApi.generateQuiz(
        document.id,
        numQuestions,
        difficulty,
        questionType,
        force
      );
      setQuiz(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to generate quiz.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectOption = (qId: number, optionId: string) => {
    if (quiz?.completed) return; // Cannot change after submit
    setUserAnswers((prev) => ({ ...prev, [qId]: optionId }));
  };

  const handleSubmitQuiz = async () => {
    if (!quiz) return;
    try {
      setIsSubmitting(true);
      setError(null);
      const evaluated = await studyApi.submitQuiz(quiz.id, userAnswers);
      setQuiz(evaluated);
      setCurrentIndex(0); // Jump to first question for review
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to submit quiz.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const activeQuestion: QuizQuestion | undefined = quiz?.questions[currentIndex];
  const totalQuestions = quiz?.questions.length || 0;
  const answeredCount = Object.keys(userAnswers).length;
  const progressPercent = totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0;

  return (
    <div className="relative flex-1 min-h-0 overflow-y-auto p-6 md:p-8 max-w-4xl mx-auto w-full">
      {/* Header Banner */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-950/60 px-2.5 py-1 rounded-md border border-brand-200 dark:border-brand-800">
                Interactive Assessment
              </span>
              {quiz?.completed && (
                <span className="text-xs font-bold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-1 rounded-md border border-emerald-200 dark:border-emerald-800/60 flex items-center space-x-1">
                  <Award className="w-3.5 h-3.5" />
                  <span>Score: {quiz.score} / {quiz.total_questions} ({quiz.percentage}%)</span>
                </span>
              )}
            </div>
            <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100 mt-2">
              {quiz?.title || `Quiz: ${document.original_filename}`}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Document: {document.original_filename} • Difficulty: {quiz?.difficulty || difficulty}
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-semibold flex items-center space-x-1.5 transition-all"
              title="Configure Quiz Settings"
            >
              <Sliders className="w-4 h-4" />
              <span>Configure</span>
            </button>

            <button
              onClick={() => handleGenerateQuiz(true)}
              disabled={isLoading || document.status !== 'ready'}
              className="flex items-center space-x-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 dark:disabled:text-slate-600 text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Creating...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Generate New Quiz</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Configuration Panel */}
        {showConfig && (
          <div className="mt-5 pt-5 border-t border-slate-100 dark:border-slate-800 grid grid-cols-1 sm:grid-cols-3 gap-4 bg-slate-50 dark:bg-slate-800/70 p-4 rounded-xl">
            <div>
              <label className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider block mb-1.5">
                Questions
              </label>
              <div className="flex space-x-2">
                {[5, 10, 15].map((cnt) => (
                  <button
                    key={cnt}
                    onClick={() => setNumQuestions(cnt)}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      numQuestions === cnt
                        ? 'bg-brand-600 text-white shadow-sm'
                        : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                    }`}
                  >
                    {cnt}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider block mb-1.5">
                Difficulty
              </label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as any)}
                className="w-full text-xs font-medium bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
                <option value="mixed">Mixed</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider block mb-1.5">
                Question Type
              </label>
              <select
                value={questionType}
                onChange={(e) => setQuestionType(e.target.value as any)}
                className="w-full text-xs font-medium bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="mixed">Mixed (MCQ & T/F)</option>
                <option value="mcq">Single-choice MCQs</option>
                <option value="true_false">True / False</option>
              </select>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/60 rounded-xl text-xs text-red-700 dark:text-red-300 mb-6 flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Interactive Quiz Engine */}
      {isLoading && !quiz ? (
        <div className="text-center py-20 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8">
          <Loader2 className="w-10 h-10 text-brand-600 dark:text-brand-400 animate-spin mx-auto mb-4" />
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">Generating Interactive Quiz</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-sm mx-auto">
            Extracting document concepts, formulas, and plausible distractors across {document.total_pages}{' '}
            {document.citation_unit === 'section' ? 'sections' : 'pages'}...
          </p>
        </div>
      ) : quiz && quiz.questions.length > 0 ? (
        <div>
          {/* Completion Summary Score Card */}
          {quiz.completed && (
            <div className="bg-gradient-to-br from-indigo-50 to-brand-50 dark:from-indigo-950/60 dark:to-brand-950/60 border border-brand-200 dark:border-brand-800/70 rounded-2xl p-6 mb-6 text-center shadow-sm">
              <Award className="w-12 h-12 text-brand-600 dark:text-brand-400 mx-auto mb-2" />
              <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100">Quiz Complete!</h3>
              <p className="text-xs text-slate-600 dark:text-slate-300 mt-1">
                You scored <span className="font-bold text-brand-700 dark:text-brand-300">{quiz.score}</span> out of{' '}
                <span className="font-bold text-brand-700 dark:text-brand-300">{quiz.total_questions}</span> (
                <span className="font-bold text-brand-700 dark:text-brand-300">{quiz.percentage}%</span>)
              </p>
              <div className="mt-3 flex items-center justify-center space-x-3 text-xs">
                <span className="px-3 py-1 bg-white dark:bg-slate-900 rounded-full border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-medium">
                  {quiz.percentage! >= 80 ? '🌟 Excellent Understanding' : quiz.percentage! >= 60 ? '👍 Good Effort' : '📖 Review Recommended'}
                </span>
                <button
                  onClick={() => handleGenerateQuiz(true)}
                  className="px-3.5 py-1 bg-brand-600 hover:bg-brand-700 text-white rounded-full font-semibold shadow-xs flex items-center space-x-1"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Try New Set</span>
                </button>
              </div>
            </div>
          )}

          {/* Progress Header & Navigation Bar */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm mb-4">
            <div className="flex items-center justify-between mb-2 text-xs">
              <span className="font-bold text-slate-700 dark:text-slate-200">
                Question {currentIndex + 1} of {totalQuestions}
              </span>
              <span className="text-slate-500 dark:text-slate-400 font-medium">
                {answeredCount} of {totalQuestions} answered
              </span>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden mb-3">
              <div
                className="bg-brand-600 h-full rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>

            {/* Number Pills Navigation */}
            <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              {quiz.questions.map((q, idx) => {
                const isCurrent = idx === currentIndex;
                const hasAnswer = !!userAnswers[q.id];
                let pillStyle = 'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300';

                if (quiz.completed) {
                  const isCorrect = userAnswers[q.id] === q.correct_option_id;
                  pillStyle = isCorrect
                    ? 'bg-emerald-100 dark:bg-emerald-950/70 border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-200'
                    : 'bg-red-100 dark:bg-red-950/70 border-red-300 dark:border-red-700 text-red-800 dark:text-red-200';
                } else if (hasAnswer) {
                  pillStyle = 'bg-brand-50 dark:bg-brand-950/70 border-brand-300 dark:border-brand-700 text-brand-700 dark:text-brand-300 font-semibold';
                }

                if (isCurrent) {
                  pillStyle += ' ring-2 ring-brand-500 ring-offset-1 dark:ring-offset-slate-900 font-bold';
                }

                return (
                  <button
                    key={q.id}
                    onClick={() => setCurrentIndex(idx)}
                    className={`w-7 h-7 rounded-lg border text-xs flex items-center justify-center transition-all ${pillStyle}`}
                  >
                    {idx + 1}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Single Question Card */}
          {activeQuestion && (
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 md:p-8 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold text-brand-700 dark:text-brand-300 bg-brand-50 dark:bg-brand-950/60 px-2.5 py-1 rounded-md border border-brand-200 dark:border-brand-800">
                  Question {currentIndex + 1}
                </span>
                {activeQuestion.source_page && (
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">
                    Source: Page {activeQuestion.source_page}
                  </span>
                )}
              </div>

              {/* Question Text with KaTeX */}
              <div className="text-sm md:text-base font-semibold text-slate-800 dark:text-slate-100 mb-6 leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {activeQuestion.question}
                </ReactMarkdown>
              </div>

              {/* Options List */}
              <div className="space-y-3 mb-6">
                {activeQuestion.options.map((opt) => {
                  const isSelected = userAnswers[activeQuestion.id] === opt.id;
                  const isCorrect = opt.id === activeQuestion.correct_option_id;

                  let optionStyle =
                    'border-slate-200 dark:border-slate-700 hover:border-brand-300 dark:hover:border-brand-600 bg-slate-50/70 dark:bg-slate-800/60 hover:bg-slate-100/60 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200';

                  if (quiz.completed) {
                    if (isCorrect) {
                      optionStyle = 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/50 text-emerald-950 dark:text-emerald-100 font-semibold ring-1 ring-emerald-500';
                    } else if (isSelected && !isCorrect) {
                      optionStyle = 'border-red-500 bg-red-50 dark:bg-red-950/50 text-red-950 dark:text-red-100 ring-1 ring-red-500';
                    } else {
                      optionStyle = 'border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 opacity-60 text-slate-500 dark:text-slate-500';
                    }
                  } else if (isSelected) {
                    optionStyle =
                      'border-brand-600 dark:border-brand-500 bg-brand-50/60 dark:bg-brand-950/50 text-brand-900 dark:text-brand-100 font-semibold ring-1 ring-brand-600';
                  }

                  return (
                    <button
                      key={opt.id}
                      disabled={quiz.completed}
                      onClick={() => handleSelectOption(activeQuestion.id, opt.id)}
                      className={`w-full text-left p-4 rounded-xl border text-xs md:text-sm flex items-center justify-between transition-all ${optionStyle}`}
                    >
                      <div className="flex items-center space-x-3.5">
                        <span
                          className={`w-7 h-7 rounded-lg border flex items-center justify-center font-bold text-xs shadow-xs ${
                            isSelected
                              ? 'bg-brand-600 text-white border-brand-600'
                              : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200'
                          }`}
                        >
                          {opt.id}
                        </span>
                        <div className="leading-relaxed">
                          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                            {opt.text}
                          </ReactMarkdown>
                        </div>
                      </div>

                      {quiz.completed && isCorrect && (
                        <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                      )}
                      {quiz.completed && isSelected && !isCorrect && (
                        <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" />
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Explanation (Shown ONLY after submission) */}
              {quiz.completed && activeQuestion.explanation && (
                <div className="p-4 bg-slate-50 dark:bg-slate-800/70 rounded-xl border border-slate-200 dark:border-slate-700 text-xs text-slate-700 dark:text-slate-200 mb-6 leading-relaxed">
                  <div className="flex items-center space-x-1.5 font-bold text-slate-900 dark:text-slate-100 mb-1">
                    <HelpCircle className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                    <span>Explanation & Verified Document Citation:</span>
                  </div>
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {activeQuestion.explanation}
                  </ReactMarkdown>
                </div>
              )}

              {/* Navigation Controls */}
              <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-slate-800">
                <button
                  onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                  disabled={currentIndex === 0}
                  className="flex items-center space-x-1 px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                >
                  <ChevronLeft className="w-4 h-4" />
                  <span>Previous</span>
                </button>

                <div className="flex items-center space-x-2">
                  {!quiz.completed && (
                    <button
                      onClick={handleSubmitQuiz}
                      disabled={isSubmitting || answeredCount === 0}
                      className="flex items-center space-x-1.5 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 dark:disabled:text-slate-600 text-white rounded-xl text-xs font-bold shadow-sm transition-all"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Evaluating...</span>
                        </>
                      ) : (
                        <>
                          <Send className="w-3.5 h-3.5" />
                          <span>Submit Assessment</span>
                        </>
                      )}
                    </button>
                  )}

                  <button
                    onClick={() => setCurrentIndex((prev) => Math.min(totalQuestions - 1, prev + 1))}
                    disabled={currentIndex === totalQuestions - 1}
                    className="flex items-center space-x-1 px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    <span>Next</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-20 bg-white dark:bg-slate-900 border border-dashed border-slate-200 dark:border-slate-800 rounded-2xl p-8">
          <Layers className="w-12 h-12 text-slate-300 dark:text-slate-700 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800 dark:text-slate-100">Ready to Test Your Knowledge</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-sm mx-auto">
            Click 'Generate New Quiz' above to create an interactive MCQ assessment from {document.original_filename}.
          </p>
        </div>
      )}
    </div>
  );
};
