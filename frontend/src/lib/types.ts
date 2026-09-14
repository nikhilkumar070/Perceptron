export type Role = "student" | "tpo";
export interface UserPublic { id:string; name:string; email:string; role:Role; profile_complete:boolean }
export interface SkillScore { category:string; score:number; label:string }
export interface RoadmapTask { id:string; title:string; category:string; difficulty:string; estimated_minutes:number; status:"todo"|"done"; date:string; details:string }
export interface TpoSummary { total_students:number; average_readiness:number; average_assessment:number; roadmap_completion:number; top_skill_gaps:{category:string;students:number}[]; students_needing_support:number; filters:{branches:string[];graduation_years:number[];target_roles:string[]} }
export interface ResumeAnalysis { id:string; filename:string; target_role:string; created_at:string; result: { score:number; engine:string; summary:string; strengths:string[]; gaps:string[]; suggestions:string[]; ats_keywords_matched:string[]; ats_keywords_missing:string[]; rewrites:{before:string;after:string}[]; word_count:number; sections:Record<string,boolean> } }
