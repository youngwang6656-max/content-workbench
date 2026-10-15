from datetime import datetime
from zoneinfo import ZoneInfo
from waypoint.contracts import uid,now
class Budget:
    def __init__(self,repo):self.repo=repo
    def month(self):return datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m')
    def summary(self):
        rows=self.repo.list('budget',month=self.month())
        used=sum(x.get('actual',0) or 0 for x in rows)
        reserved=sum(x['reserved'] for x in rows if x['state'] in ['reserved','unknown'])
        return {'month':self.month(),'used_microusd':used,'reserved_microusd':reserved,
                'unknown':any(x['state']=='unknown' for x in self.repo.list('budget')),'limit_microusd':20_000_000,
                'stop_microusd':self.repo.settings()['stop_microusd'],'entries':rows+[x for x in self.repo.list('budget') if x['state']=='unknown' and x['month']!=self.month()]}
    def reserve(self,job_id,estimated_upper_microusd):
        if type(estimated_upper_microusd) is not int or estimated_upper_microusd<0:raise ValueError('价格或费用未知，已暂停付费调用')
        with self.repo.db.lock,self.repo.db.conn:
            existing=self.repo.list('budget',job_id=job_id)
            if existing:raise ValueError('该请求已有费用记录，不能静默重复调用')
            s=self.summary()
            if s['unknown']:raise ValueError('存在待核实费用，已暂停新的付费调用')
            if s['used_microusd']+s['reserved_microusd']+estimated_upper_microusd>s['stop_microusd']:raise ValueError('本次调用将超过预算停止线')
            d={'id':uid(),'job_id':job_id,'month':self.month(),'reserved':estimated_upper_microusd,'actual':None,'state':'reserved','created_at':now()}
            self.repo._put('budget',d);return d
    def settle(self,id,actual_microusd):
        if actual_microusd is not None and (type(actual_microusd) is not int or actual_microusd<0):raise ValueError('费用无效')
        with self.repo.db.lock,self.repo.db.conn:
            d=self.repo._get(id,'budget')
            if d['state']=='settled':return
            d.update(actual=actual_microusd,state='unknown' if actual_microusd is None else 'settled')
            self.repo._put('budget',d)
    def add_external(self,amount,note):
        if type(amount) is not int or amount<0 or not note.strip():raise ValueError('请填写有效金额与说明')
        return self.repo.put('budget',{'id':uid(),'job_id':uid(),'month':self.month(),'reserved':0,'actual':amount,'state':'settled','note':note,'created_at':now()})
